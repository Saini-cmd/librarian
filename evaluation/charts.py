"""
Static matplotlib figures for the evaluation reports (academic journal style).

Figures are rendered headless to PNG bytes for embedding into the self-contained
HTML report (and written to disk as PNG files for the Markdown report).

- grouped_bar_chart — the three retrieval metrics per setup (S1-S4)
- delta_chart       — component contributions: S2-S1 (chunking), S3-S2 (hybrid),
                      S4-S3 (rerank)
- recall_curve_chart — Recall@K for K = 1..K across setups
- aggregate_chart    — one metric per repo across multiple evaluated repos
"""

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


SETUP_ORDER = ["S1", "S2", "S3", "S4"]
SETUP_COLORS = {
    "S1": "#8a8f98",
    "S2": "#4c78a8",
    "S3": "#72b7b2",
    "S4": "#54a24b",
}

RETRIEVAL_METRICS = ["context_recall", "context_precision", "mrr", "recall_at_k"]
RETRIEVAL_LABELS = {
    "context_recall": "Context Recall",
    "context_precision": "Context Precision",
    "mrr": "MRR",
    "recall_at_k": "Recall@K",
}
_METRIC_COLORS = {
    "context_recall": "#4c78a8",
    "context_precision": "#72b7b2",
    "mrr": "#e45756",
    "recall_at_k": "#54a24b",
}


def _style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.grid": True,
            "grid.alpha": 0.25,
            "grid.linestyle": ":",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "font.size": 10,
            "font.family": "sans-serif",
        }
    )


def _fig_to_png(fig, dpi: int = 160) -> bytes:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return buffer.getvalue()


def _grouped_bars(ax, x, components, value_lookup):
    width = 0.2
    for j, metric in enumerate(RETRIEVAL_METRICS):
        values = [value_lookup(c, metric) for c in components]
        ax.bar(
            [xi + (j - 1.5) * width for xi in range(len(components))],
            values,
            width=width,
            label=RETRIEVAL_LABELS[metric],
            color=_METRIC_COLORS[metric],
            alpha=0.9,
        )
    ax.set_xticks(range(len(components)))
    ax.set_xticklabels(components)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Score")
    ax.legend(frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.1))


def grouped_bar_chart(scores: dict[str, dict[str, float]]) -> bytes:
    """``scores``: setup -> {context_recall, context_precision, recall_at_k}."""
    _style()
    setups = [s for s in SETUP_ORDER if s in scores]
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    _grouped_bars(ax, setups, setups, lambda s, m: scores[s].get(m, 0.0))
    ax.set_title("Retrieval metrics across pipeline setups")
    return _fig_to_png(fig)


def delta_chart(deltas: dict[str, dict[str, float]]) -> bytes:
    """``deltas``: component -> {metric: value}; e.g. {"S2 − S1": {...}}."""
    _style()
    components = list(deltas)
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    width = 0.2
    for j, metric in enumerate(RETRIEVAL_METRICS):
        values = [deltas[c].get(metric, 0.0) for c in components]
        ax.bar(
            [xi + (j - 1.5) * width for xi in range(len(components))],
            values,
            width=width,
            label=RETRIEVAL_LABELS[metric],
            color=_METRIC_COLORS[metric],
            alpha=0.9,
        )
    ax.axhline(0.0, color="black", linewidth=0.8)
    ax.set_xticks(range(len(components)))
    ax.set_xticklabels(components)
    ax.set_ylabel("Δ score")
    ax.legend(frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.1))
    ax.set_title("Component contributions")
    return _fig_to_png(fig)


def recall_curve_chart(curve: dict[str, list[float]]) -> bytes:
    """``curve``: setup -> [recall@1, recall@2, ..., recall@K]."""
    _style()
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    for setup in SETUP_ORDER:
        values = curve.get(setup)
        if not values:
            continue
        ax.plot(
            range(1, len(values) + 1),
            values,
            marker="o",
            markersize=3,
            linewidth=1.6,
            label=setup,
            color=SETUP_COLORS[setup],
        )
    ax.set_xlabel("K")
    ax.set_ylabel("Recall@K")
    ax.set_ylim(0, 1)
    ax.legend(frameon=False)
    ax.set_title("Recall@K as K grows")
    return _fig_to_png(fig)


def aggregate_chart(summaries: list[dict], metric: str = "recall_at_k") -> bytes:
    """``summaries``: [{repo_name, context_recall, context_precision, recall_at_k}].

    One bar per repo for a single retrieval metric.
    """
    _style()
    repos = [s["repo_name"] for s in summaries]
    values = [s.get(metric, 0.0) for s in summaries]
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    ax.bar(repos, values, color="#4c78a8", alpha=0.9, width=0.6)
    ax.set_ylabel(RETRIEVAL_LABELS[metric])
    ax.set_ylim(0, 1)
    ax.set_title(f"{RETRIEVAL_LABELS[metric]} by repository (best setup)")
    plt.xticks(rotation=15, ha="right")
    return _fig_to_png(fig)


def render_figures(
    scores: dict[str, dict[str, float]],
    deltas: dict[str, dict[str, float]],
    curve: dict[str, list[float]],
) -> dict[str, bytes]:
    """Convenience: produce the standard single-repo figures."""
    return {
        "grouped_bars": grouped_bar_chart(scores),
        "deltas": delta_chart(deltas),
        "recall_curve": recall_curve_chart(curve),
    }
