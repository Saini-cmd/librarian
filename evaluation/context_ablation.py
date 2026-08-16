"""
Context-curation ablation: compare S4 answer quality across context policies.

Runs answer generation on a cached golden set under several ``ContextBuilder``
policies and prints a comparison table: Faithfulness / Answer Relevance /
average context tokens / average context chunks / % of questions where the
relevant chunk survived into the context.

Reuses the already-embedded eval collections + cached golden set, so the only
cost is one answer + two judge calls per (question, policy).

Usage:
    python -m evaluation.context_ablation \
        --golden evaluation/datasets/lynko_golden.json
"""

import argparse
import logging
import statistics
from dataclasses import dataclass, field

from evaluation.golden_set import GoldenItem, load_golden_set
from evaluation.ingest import EVAL_AST_COLLECTION, EVAL_NAIVE_COLLECTION
from evaluation.llm_judge import Judge
from evaluation.metrics import chunk_relevant
from evaluation.pipelines import EvalPipelines
from rag.context_builder import ContextBuilder
from rag.llm_client import LLMClient
from rag.prompt_builder import PromptBuilder


POLICIES: dict[str, dict] = {
    "baseline (max 8)": {"max_chunks": 8},
    "ratio 0.3": {"max_chunks": 8, "min_score_ratio": 0.3},
    "ratio 0.4": {"max_chunks": 8, "min_score_ratio": 0.4},
    "ratio 0.4 + per-file 2": {"max_chunks": 8, "min_score_ratio": 0.4, "max_per_file": 2},
    "max 5 + ratio 0.4": {"max_chunks": 5, "min_score_ratio": 0.4},
}


@dataclass
class PolicyResult:
    faithfulness: list[float] = field(default_factory=list)
    relevance: list[float] = field(default_factory=list)
    tokens: list[int] = field(default_factory=list)
    chunks: list[int] = field(default_factory=list)
    relevant_survived: int = 0
    total: int = 0


def _run_policy(
    items: list[GoldenItem],
    retrieved_by_item: dict[str, list[dict]],
    policy: dict,
) -> PolicyResult:
    context_builder = ContextBuilder(**policy)
    prompt_builder = PromptBuilder()
    llm = LLMClient()
    judge = Judge()
    result = PolicyResult()

    for item in items:
        retrieved = retrieved_by_item[item.id]
        context = context_builder.build(retrieved)
        result.tokens.append(context.total_tokens)
        result.chunks.append(len(context.chunks))
        result.total += 1

        if any(chunk_relevant(c.chunk, item) for c in context.chunks):
            result.relevant_survived += 1

        try:
            prompt = prompt_builder.build(
                query=item.query, context=context, repo_hash=item.repo_hash
            )
            answer = llm.generate(prompt.messages).text
        except Exception:
            logging.getLogger(__name__).exception("ablation_item_failed id=%s", item.id)
            continue

        faithfulness = judge.faithfulness(item.query, answer, [c.chunk.content for c in context.chunks])
        relevance = judge.answer_relevance(item.query, answer)

        if faithfulness is not None:
            result.faithfulness.append(faithfulness)
        if relevance is not None:
            result.relevance.append(relevance)

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Context-curation ablation.")
    parser.add_argument("--golden", required=True, help="Path to the cached golden-set JSON.")
    parser.add_argument("--k", type=int, default=8, help="Retrieval depth (default 8).")
    parser.add_argument("--verbose", action="store_true", help="Enable INFO logs.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)

    items = load_golden_set(args.golden)
    repo_hashes = {item.repo_hash for item in items}
    if len(repo_hashes) != 1:
        print(f"ERROR: golden set spans {len(repo_hashes)} commits; expected one.")
        return 2
    repo_hash = repo_hashes.pop()
    print(f"Golden set: {len(items)} questions (hash {repo_hash[:10]})")

    pipelines = EvalPipelines(
        naive_collection=EVAL_NAIVE_COLLECTION,
        ast_collection=EVAL_AST_COLLECTION,
        final_top_k=args.k,
    )
    retrieved_by_item: dict[str, list[dict]] = {}
    for item in items:
        retrieved_by_item[item.id] = pipelines.retrieve("S4", item.query, repo_hash)

    results = {name: _run_policy(items, retrieved_by_item, policy) for name, policy in POLICIES.items()}

    print()
    print(f"{'Policy':<26} {'Faith.':>7} {'Relev.':>7} {'Tokens':>7} {'Chunks':>7} {'Rel.Surv':>8}")
    print("-" * 74)
    for name, r in results.items():
        mean = lambda xs: statistics.mean(xs) if xs else float("nan")
        print(
            f"{name:<26} {mean(r.faithfulness):7.3f} {mean(r.relevance):7.3f} "
            f"{mean(r.tokens):7.1f} {mean(r.chunks):7.1f} "
            f"{r.relevant_survived / r.total:8.0%}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
