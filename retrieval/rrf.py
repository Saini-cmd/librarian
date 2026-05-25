from collections.abc import Iterable


def reciprocal_rank_fusion(
    ranked_lists: list[Iterable[str]],
    k: int = 60,
) -> dict[str, float]:
    """
    Compute Reciprocal Rank Fusion scores.

    score(doc) = sum(1 / (k + rank_i(doc)))
    """
    scores: dict[str, float] = {}

    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + (1.0 / (k + rank))

    return scores
