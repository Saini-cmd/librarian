"""
Evaluation harness CLI.

Usage:
    python -m evaluation.cli --repo https://github.com/Saini-cmd/lynko
    python -m evaluation.cli --repo <url1> --repo <url2> --k 10 --n 30
    python -m evaluation.cli --config eval_config.json

Per repo it ingests (naive + AST), builds/loads a cached golden set, runs S1-S4,
scores the six metrics, generates answers on S4, and writes a professional
report (JSON / Markdown / self-contained HTML / PDF with figures) under
``data/eval_reports/<repo>_<ts>/``. PDF is rendered via WeasyPrint when
available (gracefully skipped otherwise, D35). With multiple repos an aggregate
report is also written.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

from evaluation import metrics as metrics_mod
from evaluation.charts import aggregate_chart, render_figures
from evaluation.golden_set import (
    GoldenItem,
    build_golden_set,
    load_golden_set,
    save_golden_set,
    select_entities,
)
from evaluation.ingest import (
    EVAL_AST_COLLECTION,
    EVAL_NAIVE_COLLECTION,
    EvalIngestResult,
    ingest_repo_for_eval,
)
from evaluation.llm_judge import Judge
from evaluation.pipelines import (
    EMBEDDING_MODEL,
    RERANK_MODEL,
    EvalPipelines,
    build_setup_metadata,
)
from evaluation.report import (
    EvalReport,
    GenerationResult,
    ItemDetail,
    RepoSummary,
    ReportMeta,
    SetupResult,
    build_meta,
    write_aggregate,
    write_report,
)
from rag.answer_generator import AnswerGenerator
from rag.llm_client import LLMClient


logger = logging.getLogger(__name__)

DATASETS_DIR = Path(__file__).resolve().parent / "datasets"
DEFAULT_OUT = Path("data/eval_reports")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="evaluation",
        description="URL-driven RAG pipeline evaluation with academic reports.",
    )
    parser.add_argument(
        "--repo",
        action="append",
        default=None,
        metavar="URL",
        help="Repository URL to evaluate (repeatable).",
    )
    parser.add_argument("--config", type=Path, default=None, help="JSON config file.")
    parser.add_argument("--k", type=int, default=8, help="Final retrieval depth K (default 8).")
    parser.add_argument("--n", type=int, default=20, help="Golden-set size N (default 20).")
    parser.add_argument("--seed", type=int, default=42, help="Sampling seed (default 42).")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Reports output dir.")
    parser.add_argument("--regenerate-golden", action="store_true", help="Rebuild the golden set.")
    parser.add_argument("--no-embed", action="store_true", help="Skip embedding (expects prior ingest).")
    parser.add_argument("--skip-generation", action="store_true", help="Skip S4 answer generation + judges.")
    parser.add_argument("--verbose", action="store_true", help="Enable INFO logging.")
    return parser.parse_args(argv)


def _apply_config(args: argparse.Namespace) -> argparse.Namespace:
    if args.config is None:
        return args
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if not args.repo and config.get("repos"):
        args.repo = config["repos"]
    args.k = args.k if args.k != 8 or "k" not in config else config["k"]
    args.n = args.n if args.n != 20 or "n" not in config else config["n"]
    args.seed = args.seed if args.seed != 42 or "seed" not in config else config["seed"]
    if "out" in config:
        args.out = Path(config["out"])
    return args


def _golden_path(repo_name: str) -> Path:
    return DATASETS_DIR / f"{repo_name}_golden.json"


def _load_or_build_golden(
    repo_name: str,
    ast_chunks,
    n: int,
    seed: int,
    regenerate: bool,
) -> list[GoldenItem]:
    path = _golden_path(repo_name)
    if path.exists() and not regenerate:
        items = load_golden_set(path)
        logger.info("golden_set_loaded path=%s count=%d", path, len(items))
        return items

    entities = select_entities(ast_chunks, n=n, seed=seed)
    if not entities:
        raise RuntimeError(
            f"No evaluable AST entities found in {repo_name}; nothing to build a golden set from."
        )
    llm = LLMClient()
    items = build_golden_set(entities, llm, id_prefix=repo_name)
    save_golden_set(items, path)
    logger.info("golden_set_built path=%s count=%d", path, len(items))
    return items


def _stage(label: str) -> None:
    print(f"\n== {label} ==")


def run_repo(
    repo_url: str,
    k: int = 8,
    n: int = 20,
    seed: int = 42,
    out_root: Path = DEFAULT_OUT,
    regenerate_golden: bool = False,
    embed: bool = True,
    run_generation: bool = True,
) -> EvalReport:
    print(f"\n=== Evaluating {repo_url} ===")

    out_root = Path(out_root)

    # --- stage 1: ingest (clone + chunk + embed) ---
    _stage("1/4 Ingest (clone + chunk + embed)")
    embed_bars: dict[str, tqdm] = {}

    def _on_embed(collection: str, done: int, total: int) -> None:
        if collection not in embed_bars:
            embed_bars[collection] = tqdm(
                total=total or 1,
                desc=f"  embed {collection}",
                unit="batch",
                leave=False,
            )
        bar = embed_bars[collection]
        if total:
            bar.total = total
        bar.update(done - bar.n)
        if done >= total:
            bar.close()
            del embed_bars[collection]

    ingest_result = ingest_repo_for_eval(
        repo_url, embed=embed, progress=_on_embed if embed else None
    )
    repo_name = ingest_result.repo_name
    repo_hash = ingest_result.repo_hash
    for bar in embed_bars.values():
        bar.close()

    # --- stage 2: golden set ---
    _stage("2/4 Golden set")
    items = _load_or_build_golden(repo_name, ingest_result.ast_chunks, n, seed, regenerate_golden)
    if len(items) < n * 0.6:
        print(
            f"WARNING: golden set has only {len(items)} items (<60% of {n}) — "
            "too many paraphrased queries leaked symbol names and were dropped."
        )
    print(f"  {len(items)} questions")

    pipelines = EvalPipelines(
        naive_collection=EVAL_NAIVE_COLLECTION,
        ast_collection=EVAL_AST_COLLECTION,
        final_top_k=k,
    )
    setup_meta = build_setup_metadata(EVAL_NAIVE_COLLECTION, EVAL_AST_COLLECTION)
    collection_of = {
        "S1": EVAL_NAIVE_COLLECTION,
        "S2": EVAL_AST_COLLECTION,
        "S3": EVAL_AST_COLLECTION,
        "S4": EVAL_AST_COLLECTION,
    }
    collection_chunks = {
        EVAL_NAIVE_COLLECTION: ingest_result.naive_chunks,
        EVAL_AST_COLLECTION: ingest_result.ast_chunks,
    }

    # --- stage 3: retrieval per (item, setup) ---
    _stage("3/4 Retrieval (S1–S4)")
    retrieved_by_item: dict[str, dict[str, list[dict]]] = {}
    per_item_metrics: dict[str, dict[str, metrics_mod.ItemMetricResult]] = {}
    with tqdm(total=len(items) * 4, desc="  retrieving", unit="query", leave=False) as bar:
        for item in items:
            retrieved_by_item[item.id] = {}
            per_item_metrics[item.id] = {}
            for setup in ("S1", "S2", "S3", "S4"):
                retrieved = pipelines.retrieve(setup, item.query, repo_hash)
                retrieved_by_item[item.id][setup] = retrieved
                per_item_metrics[item.id][setup] = metrics_mod.compute_item_retrieval(
                    retrieved,
                    item,
                    collection_chunks[collection_of[setup]],
                    k=k,
                    setup=setup,
                )
                bar.update(1)

    # --- aggregates per setup ---
    scores: dict[str, dict[str, float]] = {}
    for setup in ("S1", "S2", "S3", "S4"):
        results = [per_item_metrics[item.id][setup] for item in items]
        scores[setup] = metrics_mod.aggregate_retrieval(results)

    # --- recall curve (binary hit rate at each K) ---
    curve: dict[str, list[float]] = {}
    for setup in ("S1", "S2", "S3", "S4"):
        curve[setup] = [
            sum(
                metrics_mod.recall_hit_at_k(
                    retrieved_by_item[item.id][setup], item, k_idx
                )
                for item in items
            )
            / len(items)
            for k_idx in range(1, k + 1)
        ]

    # --- generation (S4 only) ---
    judge = Judge()
    answer_gen = AnswerGenerator()
    generation = None
    gen_by_item: dict[str, dict] = {}
    if run_generation:
        _stage("4/4 Generation + judging (S4)")
        sanity = judge.sanity_check()
        for name, result in sanity.items():
            status = "PASS" if result["pass"] else "FAIL"
            print(
                f"  Judge sanity [{name}]: {status} "
                f"(good={result['good']}, bad={result['bad']})"
            )

        faithfulness_scores: list[float] = []
        relevance_scores: list[float] = []
        target_in_context = 0
        with tqdm(total=len(items), desc="  generating", unit="item", leave=False) as bar:
            for item in items:
                retrieved = retrieved_by_item[item.id]["S4"]
                try:
                    result = answer_gen.generate(item.query, retrieved, repo_hash=repo_hash)
                except Exception:
                    logger.exception("answer_generation_failed item=%s", item.id)
                    bar.update(1)
                    continue

                contexts = [c.chunk.content for c in result.context_chunks]
                f_score = judge.faithfulness(item.query, result.answer, contexts)
                r_score = judge.answer_relevance(item.query, result.answer)

                if any(
                    metrics_mod.chunk_relevant(c.chunk, item)
                    for c in result.context_chunks
                ):
                    target_in_context += 1

                if f_score is not None:
                    faithfulness_scores.append(f_score)
                if r_score is not None:
                    relevance_scores.append(r_score)

                gen_by_item[item.id] = {
                    "faithfulness": f_score,
                    "answer_relevance": r_score,
                }
                bar.update(1)

        generation = GenerationResult(
            faithfulness=metrics_mod.mean(faithfulness_scores),
            answer_relevance=metrics_mod.mean(relevance_scores),
            total_items=len(items),
            target_in_context=target_in_context / len(items) if items else 0.0,
        )

    # --- assemble report ---
    setup_results = [
        SetupResult(
            name=setup,
            description=setup_meta[setup].description,
            collection=setup_meta[setup].collection,
            context_recall=scores[setup]["context_recall"],
            context_precision=scores[setup]["context_precision"],
            mrr=scores[setup]["mrr"],
            recall_at_k=scores[setup]["recall_at_k"],
            context_recall_std=scores[setup]["context_recall_std"],
            context_precision_std=scores[setup]["context_precision_std"],
            mrr_std=scores[setup]["mrr_std"],
            recall_at_k_std=scores[setup]["recall_at_k_std"],
        )
        for setup in ("S1", "S2", "S3", "S4")
    ]

    item_details = [
        ItemDetail(
            item_id=item.id,
            query=item.query,
            file_path=item.file_path,
            start_line=item.start_line,
            end_line=item.end_line,
            symbol=item.symbol,
            language=item.language,
            setup_scores={
                setup: {
                    "context_recall": per_item_metrics[item.id][setup].context_recall,
                    "context_precision": per_item_metrics[item.id][setup].context_precision,
                    "mrr": per_item_metrics[item.id][setup].mrr,
                    "recall_at_k": per_item_metrics[item.id][setup].recall_at_k,
                }
                for setup in ("S1", "S2", "S3", "S4")
            },
            faithfulness=(gen_by_item.get(item.id) or {}).get("faithfulness"),
            answer_relevance=(gen_by_item.get(item.id) or {}).get("answer_relevance"),
        )
        for item in items
    ]

    meta = build_meta(
        repo_name=repo_name,
        repo_url=repo_url,
        repo_hash=repo_hash,
        k=k,
        n=len(items),
        embedding_model=EMBEDDING_MODEL,
        rerank_model=RERANK_MODEL,
        judge_model="deepseek-chat",
    )
    report = EvalReport(
        meta=meta,
        setups=setup_results,
        generation=generation,
        items=item_details,
        recall_curve=curve,
    )

    # --- figures + write ---
    _stage("Done — writing report")
    figures = render_figures(scores, deltas_for(scores), curve)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = out_root / f"{repo_name}_{timestamp}"
    written = write_report(report, figures, out_dir)
    print(f"Report written: {out_dir}")
    for kind, path in written.items():
        print(f"  {kind}: {path}")

    return report


def deltas_for(scores: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    def diff(a: str, b: str) -> dict[str, float]:
        return {
            metric: scores[b][metric] - scores[a][metric]
            for metric in ("context_recall", "context_precision", "mrr", "recall_at_k")
        }

    return {
        "S2 − S1 (semantic chunking)": diff("S1", "S2"),
        "S3 − S2 (hybrid retrieval)": diff("S2", "S3"),
        "S4 − S3 (reranking)": diff("S3", "S4"),
    }


def run_aggregate(reports: list[EvalReport], out_root: Path) -> None:
    if len(reports) < 2:
        return
    summaries: list[RepoSummary] = []
    for report in reports:
        best = max(report.setups, key=lambda s: s.recall_at_k)
        g = report.generation
        summaries.append(
            RepoSummary(
                repo_name=report.meta.repo_name,
                repo_url=report.meta.repo_url,
                best_setup=best.name,
                context_recall=best.context_recall,
                context_precision=best.context_precision,
                mrr=best.mrr,
                recall_at_k=best.recall_at_k,
                faithfulness=g.faithfulness if g else None,
                answer_relevance=g.answer_relevance if g else None,
            )
        )
    figure = aggregate_chart(
        [{"repo_name": s.repo_name, "recall_at_k": s.recall_at_k} for s in summaries]
    )
    out_dir = out_root / f"aggregate_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    written = write_aggregate(summaries, {"aggregate_chart": figure}, out_dir)
    print(f"\nAggregate report: {out_dir}")
    for kind, path in written.items():
        print(f"  {kind}: {path}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    _apply_config(args)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if not args.repo:
        print("No repositories given. Pass --repo <url> or --config with \"repos\".")
        return 2

    reports: list[EvalReport] = []
    for repo_url in args.repo:
        try:
            report = run_repo(
                repo_url,
                k=args.k,
                n=args.n,
                seed=args.seed,
                out_root=args.out,
                regenerate_golden=args.regenerate_golden,
                embed=not args.no_embed,
                run_generation=not args.skip_generation,
            )
            reports.append(report)
        except Exception:
            logger.exception("repo_failed url=%s", repo_url)
            print(f"ERROR evaluating {repo_url} (see log); continuing.")

    run_aggregate(reports, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
