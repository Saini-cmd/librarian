import logging
from typing import Any

from embedding.api_embedder import APIEmbedder
from rag.types import HybridCandidate
from reranking.openrouter_reranker import OpenRouterReranker
from retrieval.bm25_index import BM25Index
from retrieval.hybrid_retriever import HybridRetriever
from retrieval.post_retrieval import PostRetrievalProcessor
from retrieval.query_expander import QueryExpander
from retrieval.vector_retriever import VectorRetriever


logger = logging.getLogger(__name__)


class RetrievalPipeline:
    """
    Production retrieval flow:
    1) Query embedding (via OpenRouter API)
    2) Dense vector retrieval (Qdrant)
    3) BM25 keyword retrieval
    4) RRF merge
    5) Cross-encoder rerank
    """

    def __init__(
        self,
        collection_name: str = "code_chunks",
        vector_top_k: int = 20,
        bm25_top_k: int = 20,
        rrf_k: int = 60,
        rrf_top_k: int = 30,
        final_top_k: int = 8,
    ):
        self.final_top_k = final_top_k

        self.query_expander = QueryExpander()
        self.query_embedder = APIEmbedder(model="BAAI/bge-base-en-v1.5")
        self.vector_retriever = VectorRetriever(
            collection_name=collection_name,
            top_k=vector_top_k,
        )
        self.bm25_index = BM25Index(
            collection_name=collection_name,
            top_k=bm25_top_k,
        )
        self.hybrid_retriever = HybridRetriever(
            vector_retriever=self.vector_retriever,
            bm25_index=self.bm25_index,
            vector_top_k=vector_top_k,
            bm25_top_k=bm25_top_k,
            rrf_k=rrf_k,
            rrf_top_k=rrf_top_k,
        )
        self.post_processor = PostRetrievalProcessor()
        self.reranker = OpenRouterReranker(model="cohere/rerank-4-fast")

    def retrieve(
        self, query: str, repo_hash: str | None = None
    ) -> list[dict[str, Any]]:
        logger.info("stage=retrieval_start hash=%s", repo_hash or "all")

        expanded_query = self.query_expander.expand(query)

        query_vector = self.query_embedder.embed_query(expanded_query)

        retrieval_result = self.hybrid_retriever.retrieve(
            query=expanded_query,
            query_vector=query_vector,
            repo_hash=repo_hash,
        )
        logger.info("stage=vector_retrieved count=%d", retrieval_result.vector_count)
        logger.info("stage=bm25_retrieved count=%d", retrieval_result.bm25_count)

        adjusted_candidates = self.post_processor.adjust_scores(retrieval_result.candidates)
        deduped_candidates = self.post_processor.dedupe_candidates(adjusted_candidates)
        logger.info(
            "stage=deduplicate_candidates before=%d after=%d",
            len(adjusted_candidates),
            len(deduped_candidates),
        )

        try:
            reranked = self.reranker.rerank(
                query=query,
                candidates=deduped_candidates,
                top_k=max(self.final_top_k * 3, self.final_top_k),
            )
            final_results = self.post_processor.dedupe_reranked(reranked, top_k=self.final_top_k)
            for item in final_results:
                item["reranked"] = True
            logger.info("stage=rerank_ok count=%d", len(final_results))
        except Exception:
            logger.warning(
                "stage=rerank_failed falling_back_to_hybrid candidates=%d",
                len(deduped_candidates),
                exc_info=True,
            )
            final_results = [
                self._candidate_to_result(c)
                for c in deduped_candidates[: self.final_top_k]
            ]
            for item in final_results:
                item["reranked"] = False

        logger.info("stage=final_returned count=%d", len(final_results))
        return final_results

    @staticmethod
    def _candidate_to_result(candidate: HybridCandidate) -> dict[str, Any]:
        return {
            "chunk": candidate.chunk,
            "score": float(
                candidate.adjusted_score
                if candidate.adjusted_score is not None
                else candidate.rrf_score
            ),
            "rrf_score": float(candidate.rrf_score),
            "vector_score": candidate.vector_score,
            "bm25_score": candidate.bm25_score,
        }
