"""
Report data model and renderers (JSON / Markdown / self-contained HTML).

The runner (Phase 6) builds an :class:`EvalReport` and calls :func:`write_report`
to emit ``report.json``, ``report.md``, and ``report.html`` plus the figure PNGs.
"""

import base64
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from evaluation.charts import RETRIEVAL_LABELS, SETUP_ORDER


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReportMeta:
    repo_name: str
    repo_url: str
    repo_hash: str
    generated_at: str
    k: int
    n: int
    embedding_model: str
    rerank_model: str
    judge_model: str


@dataclass(frozen=True)
class SetupResult:
    name: str
    description: str
    collection: str
    context_recall: float
    context_precision: float
    mrr: float
    recall_at_k: float
    context_recall_std: float = 0.0
    context_precision_std: float = 0.0
    mrr_std: float = 0.0
    recall_at_k_std: float = 0.0


@dataclass(frozen=True)
class ItemDetail:
    item_id: str
    query: str
    file_path: str
    start_line: int
    end_line: int
    symbol: str
    language: str
    setup_scores: dict[str, dict] = field(default_factory=dict)
    faithfulness: float | None = None
    answer_relevance: float | None = None


@dataclass(frozen=True)
class GenerationResult:
    faithfulness: float | None
    answer_relevance: float | None
    total_items: int
    target_in_context: float = 0.0


@dataclass
class EvalReport:
    meta: ReportMeta
    setups: list[SetupResult]
    generation: GenerationResult | None
    items: list[ItemDetail]
    recall_curve: dict[str, list[float]] = field(default_factory=dict)


@dataclass(frozen=True)
class RepoSummary:
    """One evaluated repo's headline numbers for the aggregate report."""

    repo_name: str
    repo_url: str
    best_setup: str
    context_recall: float
    context_precision: float
    mrr: float
    recall_at_k: float
    faithfulness: float | None = None
    answer_relevance: float | None = None


def build_meta(
    repo_name: str,
    repo_url: str,
    repo_hash: str,
    k: int,
    n: int,
    embedding_model: str,
    rerank_model: str,
    judge_model: str,
) -> ReportMeta:
    return ReportMeta(
        repo_name=repo_name,
        repo_url=repo_url,
        repo_hash=repo_hash,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        k=k,
        n=n,
        embedding_model=embedding_model,
        rerank_model=rerank_model,
        judge_model=judge_model,
    )


def _pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.3f}"


def _pct_pm(value: float | None, std: float | None = None) -> str:
    if value is None:
        return "—"
    if std is None or std <= 0:
        return f"{value:.3f}"
    return f"{value:.3f} ± {std:.3f}"


def _setup_lookup(setups: list[SetupResult]) -> dict[str, SetupResult]:
    return {s.name: s for s in setups}


# --------------------------------------------------------------------------- #
# JSON
# --------------------------------------------------------------------------- #

def to_json(report: EvalReport) -> str:
    return json.dumps(asdict(report), indent=2)


# --------------------------------------------------------------------------- #
# Markdown
# --------------------------------------------------------------------------- #

def render_markdown(report: EvalReport) -> str:
    lines: list[str] = []
    meta = report.meta
    by_name = _setup_lookup(report.setups)

    lines.append(f"# Evaluation Report — {meta.repo_name}")
    lines.append("")
    lines.append(
        f"- **Repository**: [{meta.repo_url}]({meta.repo_url})"
    )
    lines.append(f"- **Commit**: `{meta.repo_hash[:10]}`")
    lines.append(f"- **Generated**: {meta.generated_at}")
    lines.append(f"- **Config**: K={meta.k}, golden items N={meta.n}")
    lines.append(
        f"- **Models**: embed={meta.embedding_model}, rerank={meta.rerank_model}, "
        f"judge={meta.judge_model}"
    )
    lines.append("")

    lines.append("## Retrieval results")
    lines.append("")
    lines.append("| Setup | Description | Context Recall | Context Precision | MRR | Recall@K |")
    lines.append("|---|---|---|---|---|---|")
    for s in report.setups:
        lines.append(
            f"| {s.name} | {s.description} | {_pct_pm(s.context_recall, s.context_recall_std)} | "
            f"{_pct_pm(s.context_precision, s.context_precision_std)} | "
            f"{_pct_pm(s.mrr, s.mrr_std)} | "
            f"{_pct_pm(s.recall_at_k, s.recall_at_k_std)} |"
        )
    lines.append("")
    lines.append("`±` is the per-question standard deviation — at small N the mean alone overstates certainty.")
    lines.append("")

    lines.append("## Component contributions")
    lines.append("")
    lines.append("| Component | Δ Context Recall | Δ Context Precision | Δ MRR | Δ Recall@K |")
    lines.append("|---|---|---|---|---|")
    deltas = _compute_deltas(report.setups)
    for component, values in deltas.items():
        lines.append(
            f"| {component} | {_pct(values['context_recall'])} | "
            f"{_pct(values['context_precision'])} | {_pct(values['mrr'])} | {_pct(values['recall_at_k'])} |"
        )
    lines.append("")

    lines.append("## Recall@K curve")
    lines.append("")
    lines.append("| K | " + " | ".join(s.name for s in report.setups) + " |")
    lines.append("|---|" + "---|" * len(report.setups))
    max_len = max((len(v) for v in report.recall_curve.values()), default=0)
    for k_idx in range(max_len):
        row = [str(k_idx + 1)]
        for s in report.setups:
            vals = report.recall_curve.get(s.name, [])
            row.append(_pct(vals[k_idx]) if k_idx < len(vals) else "—")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    lines.append("## How to read these numbers")
    lines.append("")
    lines.append("| Metric | What it measures | Reading it |")
    lines.append("|---|---|---|")
    lines.append("| Context Recall | How much of the ground-truth code for the question was retrieved (of all relevant chunks in the index) | Higher is better; 1.0 = every relevant chunk found |")
    lines.append("| Context Precision | How much of what was retrieved is actually relevant (noise filter) | Capped by the fixed retrieval depth: with one target entity and K=%d chunks returned per question the max is 1/K = %.3f; it measures noise, not rank quality |" % (report.meta.k, 1 / report.meta.k if report.meta.k else 0.0))
    lines.append("| MRR | Mean reciprocal rank of the first relevant chunk — how high the right code ranks | 1.0 = the right chunk is the top hit; 0 = not retrieved. The rank-quality metric |")
    lines.append("| Recall@K | How often the ground-truth entity is in the top-K results (hit rate) | 1.0 = always found in the top K; 0 = never |")
    lines.append("| Faithfulness | Whether the answer is grounded in the retrieved code (no hallucination, judge-assessed) | 1.0 = every claim supported by the retrieved context |")
    lines.append("| Answer Relevance | Whether the answer addresses the question (judge-assessed) | 1.0 = directly on-topic and complete |")
    lines.append("| Target in context | Whether the ground-truth code survived into the context fed to the LLM (S4) | 1.0 = the target code reached the LLM for every question |")
    lines.append("")
    lines.append("Deltas are setup − baseline (S2−S1, S3−S2, S4−S3): positive means the added component helped. `±` values are the per-question standard deviation.")
    lines.append("")

    if report.generation is not None:
        g = report.generation
        lines.append("## Answer generation (S4, production pipeline)")
        lines.append("")
        lines.append("| Metric | Score |")
        lines.append("|---|---|")
        lines.append(f"| Faithfulness | {_pct(g.faithfulness)} |")
        lines.append(f"| Answer Relevance | {_pct(g.answer_relevance)} |")
        lines.append(f"| Target in context | {_pct(g.target_in_context)} |")
        lines.append("")

    lines.append("## Per-query breakdown")
    lines.append("")
    lines.append(
        "| Query | File:lines | " + " | ".join(f"{s.name} R/P/MRR" for s in report.setups)
        + " | Faith. | Relev. |"
    )
    lines.append(
        "|---|----|" + "---|" * len(report.setups) + "---|---|"
    )
    for item in report.items:
        cells = [f"`{item.item_id}` {item.query}", f"`{item.file_path}:{item.start_line}-{item.end_line}`"]
        for s in report.setups:
            sc = item.setup_scores.get(s.name, {})
            cells.append(
                f"{_pct(sc.get('context_recall'))}/{_pct(sc.get('context_precision'))}/"
                f"{_pct(sc.get('mrr'))}"
            )
        cells.append(_pct(item.faithfulness))
        cells.append(_pct(item.answer_relevance))
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    lines.append("---")
    lines.append(f"Generated by the evaluation harness at {meta.generated_at}.")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #

def render_html(report: EvalReport, figure_data_uris: dict[str, str], css: str) -> str:
    meta = report.meta
    by_name = _setup_lookup(report.setups)
    deltas = _compute_deltas(report.setups)

    abstract = _build_abstract(report, deltas)

    setup_rows = "\n".join(
        f"<tr><td><strong>{s.name}</strong></td><td>{s.description}</td>"
        f"<td>{_pct_pm(s.context_recall, s.context_recall_std)}</td>"
        f"<td>{_pct_pm(s.context_precision, s.context_precision_std)}</td>"
        f"<td>{_pct_pm(s.mrr, s.mrr_std)}</td>"
        f"<td>{_pct_pm(s.recall_at_k, s.recall_at_k_std)}</td></tr>"
        for s in report.setups
    )
    delta_rows = "\n".join(
        f"<tr><td><strong>{component}</strong></td>"
        f"<td>{_pct(v['context_recall'])}</td><td>{_pct(v['context_precision'])}</td>"
        f"<td>{_pct(v['mrr'])}</td><td>{_pct(v['recall_at_k'])}</td></tr>"
        for component, v in deltas.items()
    )

    curve_rows = ""
    max_len = max((len(v) for v in report.recall_curve.values()), default=0)
    if max_len:
        header_cells = "".join(f"<th>{s.name}</th>" for s in report.setups)
        curve_rows = (
            f"<tr><th>K</th>{header_cells}</tr>"
            + "".join(
                "<tr>"
                f"<td>{k_idx + 1}</td>"
                + "".join(
                    f"<td>{_pct(report.recall_curve.get(s.name, [])[k_idx]) if k_idx < len(report.recall_curve.get(s.name, [])) else '—'}</td>"
                    for s in report.setups
                )
                + "</tr>"
                for k_idx in range(max_len)
            )
        )

    gen_block = ""
    if report.generation is not None:
        g = report.generation
        gen_block = f"""
        <section class="section">
          <h2>3. Answer generation — S4 (production pipeline)</h2>
          <div class="table-wrap">
            <table>
              <thead><tr><th>Metric</th><th>Score</th></tr></thead>
              <tbody>
                <tr><td>Faithfulness</td><td>{_pct(g.faithfulness)}</td></tr>
                <tr><td>Answer Relevance</td><td>{_pct(g.answer_relevance)}</td></tr>
                <tr><td>Target in context</td><td>{_pct(g.target_in_context)}</td></tr>
              </tbody>
            </table>
          </div>
        </section>
        """

    item_rows = ""
    for item in report.items:
        per_setup = "".join(
            f"<td>{_pct(item.setup_scores.get(s.name, {}).get('context_recall'))}/"
            f"{_pct(item.setup_scores.get(s.name, {}).get('context_precision'))}/"
            f"{_pct(item.setup_scores.get(s.name, {}).get('mrr'))}</td>"
            for s in report.setups
        )
        item_rows += (
            f"<tr><td class='mono'>{item.item_id}</td>"
            f"<td>{item.query}</td>"
            f"<td class='mono'>{item.file_path}:{item.start_line}-{item.end_line}</td>"
            f"{per_setup}"
            f"<td>{_pct(item.faithfulness)}</td><td>{_pct(item.answer_relevance)}</td></tr>"
        )

    sample_block = ""

    img = lambda name: (
        f"<figure><img src=\"{figure_data_uris.get(name, '')}\" alt=\"{name}\">"
        f"<figcaption>{_figure_caption(name)}</figcaption></figure>"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Evaluation Report — {meta.repo_name}</title>
<style>{css}</style>
</head>
<body>
<article class="paper">
  <header class="title-block">
    <p class="kicker">Code-RAG Evaluation</p>
    <h1>{meta.repo_name}</h1>
    <p class="subtitle"><a href="{meta.repo_url}">{meta.repo_url}</a></p>
    <div class="meta-grid">
      <span>Commit: <span class="mono">{meta.repo_hash[:10]}</span></span>
      <span>Generated: {meta.generated_at}</span>
      <span>K = {meta.k}</span>
      <span>Golden items N = {meta.n}</span>
    </div>
    <div class="table-wrap">
      <table class="config">
        <thead><tr><th colspan="2">Configuration</th></tr></thead>
        <tbody>
          <tr><td>Embedding model</td><td class="mono">{meta.embedding_model}</td></tr>
          <tr><td>Reranking model</td><td class="mono">{meta.rerank_model}</td></tr>
          <tr><td>Judge model</td><td class="mono">{meta.judge_model}</td></tr>
        </tbody>
      </table>
    </div>
  </header>

  <section class="section" id="abstract">
    <h2>Abstract</h2>
    <p>{abstract}</p>
  </section>

  <section class="section">
    <h2>1. Methodology</h2>
    <p>Each of the <em>N</em> golden questions targets a real code entity
    (span-based ground truth at the file/line level). For every question the four
    pipelines below retrieve a ranked list of chunks, which the deterministic
    retrieval metrics score against the golden span. Answer-level metrics are
    computed on S4 (the production pipeline) using DeepSeek as judge.</p>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Setup</th><th>Pipeline</th><th>Collection</th></tr></thead>
        <tbody>
        {''.join(f"<tr><td><strong>{s.name}</strong></td><td>{s.description}</td><td class='mono'>{s.collection}</td></tr>" for s in report.setups)}
        </tbody>
      </table>
    </div>
  </section>

  <section class="section">
    <h2>2. Results</h2>
    <h3>2.1 Retrieval metrics</h3>
    {img('grouped_bars')}
    <div class="table-wrap">
      <table>
        <thead><tr><th>Setup</th><th>Description</th><th>Context Recall</th><th>Context Precision</th><th>MRR</th><th>Recall@K</th></tr></thead>
        <tbody>{setup_rows}</tbody>
      </table>
    </div>

    <h3>2.2 Component contributions</h3>
    {img('deltas')}
    <div class="table-wrap">
      <table>
        <thead><tr><th>Component</th><th>Δ Context Recall</th><th>Δ Context Precision</th><th>Δ MRR</th><th>Δ Recall@K</th></tr></thead>
        <tbody>{delta_rows}</tbody>
      </table>
    </div>

    <h3>2.3 Recall@K curve</h3>
    {img('recall_curve')}
    <div class="table-wrap"><table>{curve_rows}</table></div>

    <h3>2.4 How to read these numbers</h3>
    <div class="legend">
      <div class="table-wrap">
        <table>
          <thead><tr><th>Metric</th><th>What it measures</th><th>Reading it</th></tr></thead>
          <tbody>
            <tr><td><strong>Context Recall</strong></td><td>How much of the ground-truth code for the question was retrieved (out of every relevant chunk in the index).</td><td>Higher is better; 1.0 = every relevant chunk was found.</td></tr>
            <tr><td><strong>Context Precision</strong></td><td>How much of what was retrieved is actually relevant — the noise filter.</td><td>Structurally capped by the retrieval depth: with one target entity and K={meta.k} chunks returned per question, the max is 1/K = 0.{int(round(1 / meta.k * 1000))}. It measures noise, not rank quality.</td></tr>
            <tr><td><strong>MRR</strong></td><td>Mean reciprocal rank of the first relevant chunk — how high the right code ranks.</td><td>1.0 = the right chunk is the top hit; lower = it appears further down; 0 = not retrieved. This is the rank-quality metric.</td></tr>
            <tr><td><strong>Recall@K</strong></td><td>How often the ground-truth entity is present in the top-K results (hit rate).</td><td>1.0 = the right code was always in the top K; 0 = never.</td></tr>
            <tr><td><strong>Faithfulness</strong></td><td>Whether the generated answer is grounded in the retrieved code — no hallucination (judge-assessed).</td><td>1.0 = every claim is supported by the retrieved context.</td></tr>
            <tr><td><strong>Answer Relevance</strong></td><td>Whether the answer actually addresses the question (judge-assessed).</td><td>1.0 = directly on-topic and complete.</td></tr>
            <tr><td><strong>Target in context</strong></td><td>Whether the ground-truth code survived into the context actually fed to the LLM (S4).</td><td>1.0 = the target code reached the LLM for every question; lower means the answer had to work without it.</td></tr>
          </tbody>
        </table>
      </div>
      <p class="note">All scores are 0–1. <strong>±</strong> values are the per-question standard deviation (higher = results vary more between questions; small golden sets mean the mean alone overstates certainty). In the per-query table, <em>R/P/MRR</em> means Context Recall / Context Precision / MRR for that setup. Deltas are setup&nbsp;−&nbsp;baseline (S2−S1, S3−S2, S4−S3), so positive means the added component helped.</p>
    </div>
  </section>

  {gen_block}

  <section class="section">
    <h2>4. Per-query breakdown</h2>
    <div class="table-wrap">
      <table class="wide">
        <thead><tr>
          <th>ID</th><th>Query</th><th>Target</th>
          {''.join(f"<th>{s.name}<br><small>R/P/MRR</small></th>" for s in report.setups)}
          <th>Faith.</th><th>Relev.</th>
        </tr></thead>
        <tbody>{item_rows}</tbody>
      </table>
    </div>
    <p class="note">R/P/MRR = Context Recall / Context Precision / MRR. Faith./Relev. apply to S4 (production) only.</p>
  </section>

  <footer class="footer">
    Generated by the evaluation harness · {meta.generated_at}
  </footer>
</article>
</body>
</html>
"""


def _figure_caption(name: str) -> str:
    return {
        "grouped_bars": "Figure 1. Retrieval metrics by pipeline setup.",
        "deltas": "Figure 2. Contribution of each pipeline component.",
        "recall_curve": "Figure 3. Recall@K as a function of K.",
    }.get(name, name)


def _compute_deltas(setups: list[SetupResult]) -> dict[str, dict[str, float]]:
    by_name = _setup_lookup(setups)

    def diff(a, b):
        if a not in by_name or b not in by_name:
            return {"context_recall": 0.0, "context_precision": 0.0, "mrr": 0.0, "recall_at_k": 0.0}
        return {
            "context_recall": by_name[b].context_recall - by_name[a].context_recall,
            "context_precision": by_name[b].context_precision - by_name[a].context_precision,
            "mrr": by_name[b].mrr - by_name[a].mrr,
            "recall_at_k": by_name[b].recall_at_k - by_name[a].recall_at_k,
        }

    return {
        "S2 − S1 (semantic chunking)": diff("S1", "S2"),
        "S3 − S2 (hybrid retrieval)": diff("S2", "S3"),
        "S4 − S3 (reranking)": diff("S3", "S4"),
    }


def _build_abstract(report: EvalReport, deltas: dict[str, dict[str, float]]) -> str:
    parts: list[str] = []
    best = max(report.setups, key=lambda s: s.recall_at_k, default=None)
    if best is not None:
        parts.append(
            f"The best retrieval configuration is <strong>{best.name}</strong> "
            f"with Recall@{report.meta.k} = {_pct(best.recall_at_k)}, "
            f"MRR = {_pct(best.mrr)}, "
            f"Context Recall = {_pct(best.context_recall)}, and "
            f"Context Precision = {_pct(best.context_precision)}."
        )
    for component, v in deltas.items():
        if "chunking" in component:
            parts.append(
                f"Semantic (AST) chunking over naive token chunks changes "
                f"Recall@{report.meta.k} by <strong>{_pct(v['recall_at_k'])}</strong>."
            )
        elif "hybrid" in component:
            parts.append(
                f"Adding lexical retrieval (BM25 + RRF) changes Recall@K by "
                f"<strong>{_pct(v['recall_at_k'])}</strong>."
            )
        elif "reranking" in component:
            parts.append(
                f"Cross-encoder reranking changes Recall@K by "
                f"<strong>{_pct(v['recall_at_k'])}</strong>."
            )
    if report.generation is not None:
        g = report.generation
        parts.append(
            f"On the production pipeline (S4), the generated answers score "
            f"Faithfulness = {_pct(g.faithfulness)} and Answer Relevance = "
            f"{_pct(g.answer_relevance)}."
        )
    return " ".join(parts)


def _load_css(css_path: str | Path | None = None) -> str:
    if css_path is None:
        css_path = Path(__file__).resolve().parent / "templates" / "report.css"
    return Path(css_path).read_text(encoding="utf-8")


def _render_pdf(html: str, out_path: str | Path, base_dir: str | Path | None = None) -> bool:
    """Render an HTML string to PDF via WeasyPrint.

    Returns ``True`` on success, ``False`` if WeasyPrint (or a system library it
    needs) is unavailable — the caller treats PDF as an optional artifact, so a
    missing dependency never fails a run.
    """
    out_path = Path(out_path)
    try:
        from weasyprint import HTML
    except ImportError:
        logger.warning("pdf_export_skipped reason=weasyprint_missing path=%s", out_path)
        return False

    try:
        HTML(string=html, base_url=str(base_dir or out_path.parent)).write_pdf(str(out_path))
    except Exception:
        logger.warning("pdf_export_skipped reason=render_failed path=%s", out_path, exc_info=True)
        return False

    logger.info("pdf_export_written path=%s", out_path)
    return True


def write_report(
    report: EvalReport,
    figures: dict[str, bytes],
    out_dir: str | Path,
    css_path: str | Path | None = None,
) -> dict[str, Path]:
    """Write ``report.json`` / ``report.md`` / ``report.html`` / ``report.pdf`` + figure PNGs."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "report.json").write_text(to_json(report), encoding="utf-8")
    (out_dir / "report.md").write_text(render_markdown(report), encoding="utf-8")

    data_uris: dict[str, str] = {}
    for name, png_bytes in figures.items():
        (out_dir / f"{name}.png").write_bytes(png_bytes)
        data_uris[name] = f"data:image/png;base64,{base64.b64encode(png_bytes).decode('ascii')}"

    css = _load_css(css_path)
    html = render_html(report, data_uris, css)
    (out_dir / "report.html").write_text(html, encoding="utf-8")

    written: dict[str, Path] = {
        "json": out_dir / "report.json",
        "md": out_dir / "report.md",
        "html": out_dir / "report.html",
    }
    if _render_pdf(html, out_dir / "report.pdf", base_dir=out_dir):
        written["pdf"] = out_dir / "report.pdf"
    return written


# --------------------------------------------------------------------------- #
# Aggregate (multi-repo)
# --------------------------------------------------------------------------- #

def render_aggregate_markdown(summaries: list[RepoSummary]) -> str:
    lines = ["# Evaluation — Aggregate Report", ""]
    lines.append("| Repository | Best Setup | Context Recall | Context Precision | MRR | Recall@K | Faithfulness | Answer Relevance |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for s in summaries:
        lines.append(
            f"| {s.repo_name} | {s.best_setup} | {_pct(s.context_recall)} | "
            f"{_pct(s.context_precision)} | {_pct(s.mrr)} | {_pct(s.recall_at_k)} | "
            f"{_pct(s.faithfulness)} | {_pct(s.answer_relevance)} |"
        )
    lines.append("")
    lines.append(f"Generated by the evaluation harness. {len(summaries)} repositories.")
    return "\n".join(lines)


def render_aggregate_html(
    summaries: list[RepoSummary],
    figure_data_uri: str,
    css: str,
) -> str:
    rows = "".join(
        f"<tr><td><strong>{s.repo_name}</strong><br><small class='mono'>{s.repo_url}</small></td>"
        f"<td>{s.best_setup}</td><td>{_pct(s.context_recall)}</td>"
        f"<td>{_pct(s.context_precision)}</td><td>{_pct(s.mrr)}</td>"
        f"<td>{_pct(s.recall_at_k)}</td>"
        f"<td>{_pct(s.faithfulness)}</td><td>{_pct(s.answer_relevance)}</td></tr>"
        for s in summaries
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Evaluation — Aggregate Report</title>
<style>{css}</style>
</head>
<body>
<article class="paper">
  <header class="title-block">
    <p class="kicker">Code-RAG Evaluation</p>
    <h1>Aggregate Report</h1>
    <p class="subtitle">{len(summaries)} repositories · production setup (S4) and best retrieval setup</p>
  </header>
  <section class="section">
    <h2>Recall@K across repositories (best setup)</h2>
    <figure>
      <img src="{figure_data_uri}" alt="aggregate">
      <figcaption>Figure 1. Recall@K by repository.</figcaption>
    </figure>
    <table>
      <thead><tr>
        <th>Repository</th><th>Best Setup</th><th>Context Recall</th>
        <th>Context Precision</th><th>MRR</th><th>Recall@K</th>
        <th>Faithfulness</th><th>Answer Relevance</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </section>
  <footer class="footer">Generated by the evaluation harness.</footer>
</article>
</body>
</html>
"""


def write_aggregate(
    summaries: list[RepoSummary],
    figures: dict[str, bytes],
    out_dir: str | Path,
    css_path: str | Path | None = None,
) -> dict[str, Path]:
    """Write ``aggregate.md`` / ``aggregate.html`` / ``aggregate.pdf`` / figure PNGs."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "aggregate.md").write_text(
        render_aggregate_markdown(summaries), encoding="utf-8"
    )

    data_uris: dict[str, str] = {}
    for name, png_bytes in figures.items():
        (out_dir / f"{name}.png").write_bytes(png_bytes)
        data_uris[name] = f"data:image/png;base64,{base64.b64encode(png_bytes).decode('ascii')}"

    css = _load_css(css_path)
    html = render_aggregate_html(summaries, data_uris.get("aggregate_chart", ""), css)
    (out_dir / "aggregate.html").write_text(html, encoding="utf-8")

    written: dict[str, Path] = {
        "md": out_dir / "aggregate.md",
        "html": out_dir / "aggregate.html",
    }
    if _render_pdf(html, out_dir / "aggregate.pdf", base_dir=out_dir):
        written["pdf"] = out_dir / "aggregate.pdf"
    return written
