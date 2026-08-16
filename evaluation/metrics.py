"""
The evaluation metrics.

Retrieval metrics (deterministic span math, no LLM):
- Context Recall    = |retrieved ∩ relevant| / |relevant in collection|
- Context Precision = |retrieved ∩ relevant| / |retrieved|
- MRR               = mean reciprocal rank of the first relevant chunk
- Recall@K          = 1 if a relevant chunk is in the top-K else 0 (binary hit)

Generation metrics (S4 only, DeepSeek-judged):
- Faithfulness      = fraction of answer claims supported by context
- Answer Relevance  = how well the answer addresses the question

The report additionally shows "Target in context" (fraction of questions whose
ground-truth code survived into the LLM context) as a diagnostic, not a metric.

Ground truth is span-based: a chunk is relevant to a ``GoldenItem`` iff it is in
the same file and its line span overlaps the item's span.

Note: Context Precision is capped at 1/K for questions with a single target
chunk (K chunks are returned per question), so it measures noise, not rank
quality — MRR is the rank-quality metric (D33).
"""

from dataclasses import dataclass
import statistics

from chunking.chunk_model import CodeChunk

from evaluation.golden_set import GoldenItem


@dataclass(frozen=True)
class ItemMetricResult:
    """Retrieval metric scores for one (golden item, setup) pair."""

    item_id: str
    setup: str
    context_recall: float
    context_precision: float
    mrr: float
    recall_at_k: float
    retrieved_count: int
    relevant_retrieved: int
    relevant_in_collection: int


def chunk_relevant(chunk: CodeChunk, item: GoldenItem) -> bool:
    """True iff ``chunk`` contains the golden item's code span.

    Uses strict overlap (``start < item.end and end > item.start``) so that a
    chunk merely touching a span boundary line (e.g. the AST chunker's gap-filler
    text chunks that share the entity's first/last line) is NOT counted as
    relevant. Without this, the S2/S3/S4 denominators inflate and recall/precision
    are distorted.
    """
    if chunk.file_path != item.file_path:
        return False
    return chunk.start_line < item.end_line and chunk.end_line > item.start_line


def relevant_in_collection(
    collection_chunks: list[CodeChunk], item: GoldenItem
) -> int:
    """Number of chunks in the whole collection that cover the golden span."""
    return sum(1 for chunk in collection_chunks if chunk_relevant(chunk, item))


def recall_hit_at_k(retrieved: list[dict], item: GoldenItem, k: int) -> float:
    """Binary Recall@K: 1.0 if a relevant chunk is in the top-K, else 0.0."""
    return (
        1.0
        if any(chunk_relevant(r["chunk"], item) for r in retrieved[:k])
        else 0.0
    )


def reciprocal_rank(retrieved: list[dict], item: GoldenItem) -> float:
    """1/rank of the first relevant chunk; 0.0 if none is retrieved.

    Rank is 1-indexed. The first relevant chunk at rank 1 scores 1.0, rank 2
    scores 0.5, etc. Unlike Context Precision, this is not capped by the fixed
    retrieval depth — a single target chunk can score 1.0 when it is the top hit.
    """
    for rank, result in enumerate(retrieved, start=1):
        if chunk_relevant(result["chunk"], item):
            return 1.0 / rank
    return 0.0


def compute_item_retrieval(
    retrieved: list[dict],
    item: GoldenItem,
    collection_chunks: list[CodeChunk],
    k: int = 8,
    setup: str = "",
) -> ItemMetricResult:
    """Score one (item, setup) retrieval result against the golden span."""
    relevant_total = relevant_in_collection(collection_chunks, item)
    relevant_retrieved = [r for r in retrieved if chunk_relevant(r["chunk"], item)]

    precision = len(relevant_retrieved) / len(retrieved) if retrieved else 0.0
    recall = len(relevant_retrieved) / relevant_total if relevant_total else 0.0

    return ItemMetricResult(
        item_id=item.id,
        setup=setup,
        context_recall=recall,
        context_precision=precision,
        mrr=reciprocal_rank(retrieved, item),
        recall_at_k=recall_hit_at_k(retrieved, item, k),
        retrieved_count=len(retrieved),
        relevant_retrieved=len(relevant_retrieved),
        relevant_in_collection=relevant_total,
    )


def aggregate_retrieval(results: list[ItemMetricResult]) -> dict[str, float]:
    """Mean retrieval metrics over a list of item results (for one setup).

    Also returns the per-item standard deviation (``*_std``) so reports can show
    the spread — at small N (12-20) a mean alone overstates certainty.
    """
    if not results:
        return {
            "context_recall": 0.0,
            "context_precision": 0.0,
            "mrr": 0.0,
            "recall_at_k": 0.0,
            "context_recall_std": 0.0,
            "context_precision_std": 0.0,
            "mrr_std": 0.0,
            "recall_at_k_std": 0.0,
        }
    return {
        "context_recall": mean([r.context_recall for r in results]),
        "context_precision": mean([r.context_precision for r in results]),
        "mrr": mean([r.mrr for r in results]),
        "recall_at_k": mean([r.recall_at_k for r in results]),
        "context_recall_std": statistics.pstdev([r.context_recall for r in results]),
        "context_precision_std": statistics.pstdev([r.context_precision for r in results]),
        "mrr_std": statistics.pstdev([r.mrr for r in results]),
        "recall_at_k_std": statistics.pstdev([r.recall_at_k for r in results]),
    }


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
