import logging

from sentence_transformers import CrossEncoder

from retrieval.hybrid_retriever import HybridCandidate


logger = logging.getLogger(__name__)


class BGEReranker:
    """Cross-encoder reranking with BAAI/bge-reranker-large."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-large",
        device: str | None = None,
        batch_size: int = 16,
    ):
        self.model_name = model_name
        self.batch_size = batch_size
        self.model = CrossEncoder(model_name, device=device)
        logger.info("Initialized BGEReranker with model=%s", model_name)

    def rerank(
        self,
        query: str,
        candidates: list[HybridCandidate],
        top_k: int = 10,
    ) -> list[dict]:
        if not candidates:
            return []

        pairs = [(query, candidate.chunk.content) for candidate in candidates]
        scores = self.model.predict(
            pairs,
            batch_size=self.batch_size,
            show_progress_bar=False,
        )

        scored = []
        for candidate, rerank_score in zip(candidates, scores):
            scored.append(
                {
                    "chunk": candidate.chunk,
                    "score": float(rerank_score),
                    "rrf_score": float(candidate.rrf_score),
                    "vector_score": candidate.vector_score,
                    "bm25_score": candidate.bm25_score,
                }
            )

        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:top_k]
