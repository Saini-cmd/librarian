import logging

from chunking.chunk_model import CodeChunk
from rag.types import HybridCandidate, HybridRetrievalResult
from retrieval.bm25_index import BM25Index
from retrieval.rrf import reciprocal_rank_fusion
from retrieval.vector_retriever import VectorRetriever


logger = logging.getLogger(__name__)


class HybridRetriever:
    """Runs vector and BM25 retrieval and merges them using RRF."""

    def __init__(
        self,
        vector_retriever: VectorRetriever,
        bm25_index: BM25Index,
        vector_top_k: int = 20,
        bm25_top_k: int = 20,
        rrf_k: int = 60,
        rrf_top_k: int = 30,
    ):
        self.vector_retriever = vector_retriever
        self.bm25_index = bm25_index
        self.vector_top_k = vector_top_k
        self.bm25_top_k = bm25_top_k
        self.rrf_k = rrf_k
        self.rrf_top_k = rrf_top_k

    def retrieve(
        self,
        query: str,
        query_vector: list[float],
        repo_hash: str | None = None,
    ) -> HybridRetrievalResult:
        vector_results = self.vector_retriever.search(
            query_vector, top_k=self.vector_top_k, repo_hash=repo_hash
        )
        bm25_results = self.bm25_index.search(
            query, top_k=self.bm25_top_k, repo_hash=repo_hash
        )

        vector_ids = [result["chunk_id"] for result in vector_results]
        bm25_ids = [result["chunk_id"] for result in bm25_results]

        fused_scores = reciprocal_rank_fusion([vector_ids, bm25_ids], k=self.rrf_k)

        chunk_map: dict[str, CodeChunk] = {}
        vector_score_map: dict[str, float] = {}
        bm25_score_map: dict[str, float] = {}

        for result in vector_results:
            chunk_map[result["chunk_id"]] = result["chunk"]
            vector_score_map[result["chunk_id"]] = float(result["score"])

        for result in bm25_results:
            chunk_map[result["chunk_id"]] = result["chunk"]
            bm25_score_map[result["chunk_id"]] = float(result["score"])

        ranked_fused = sorted(
            fused_scores.items(),
            key=lambda item: item[1],
            reverse=True,
        )[: self.rrf_top_k]

        candidates = [
            HybridCandidate(
                chunk=chunk_map[chunk_id],
                rrf_score=score,
                vector_score=vector_score_map.get(chunk_id),
                bm25_score=bm25_score_map.get(chunk_id),
            )
            for chunk_id, score in ranked_fused
            if chunk_id in chunk_map
        ]

        logger.info(
            "stage=rrf_merge vector=%d bm25=%d fused=%d",
            len(vector_results),
            len(bm25_results),
            len(candidates),
        )
        return HybridRetrievalResult(
            candidates=candidates,
            vector_count=len(vector_results),
            bm25_count=len(bm25_results),
        )
