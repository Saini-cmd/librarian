import logging
import os
from typing import Any

from reranking.bge_reranker import BGEReranker
from retrieval.bm25_index import BM25Index
from retrieval.hybrid_retriever import HybridRetriever
from retrieval.post_retrieval import PostRetrievalProcessor
from retrieval.query_expander import QueryExpander
from retrieval.query_embedder import QueryEmbedder
from retrieval.vector_retriever import VectorRetriever


logger = logging.getLogger(__name__)


class RetrievalPipeline:
    """
    Production retrieval flow:
    1) Query embedding
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
        query_device: str | None = None,
        reranker_device: str | None = None,
    ):
        self.final_top_k = final_top_k
        query_device = query_device or os.getenv("RAG_QUERY_DEVICE", "cpu")
        reranker_device = reranker_device or os.getenv("RAG_RERANKER_DEVICE", "cpu")

        self.query_expander = QueryExpander()
        self.query_embedder = QueryEmbedder(model_name="BAAI/bge-large-en-v1.5", device=query_device)
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
        self.reranker = BGEReranker(model_name="BAAI/bge-reranker-large", device=reranker_device)

    def retrieve(self, query: str) -> list[dict[str, Any]]:
        logger.info("stage=retrieval_start")

        expanded_query = self.query_expander.expand(query)

        query_vector = self.query_embedder.embed_query(expanded_query)

        retrieval_result = self.hybrid_retriever.retrieve(
            query=expanded_query,
            query_vector=query_vector,
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

        reranked = self.reranker.rerank(
            query=query,
            candidates=deduped_candidates,
            top_k=max(self.final_top_k * 3, self.final_top_k),
        )
        final_results = self.post_processor.dedupe_reranked(reranked, top_k=self.final_top_k)

        logger.info("stage=final_returned count=%d", len(final_results))
        return final_results

    def retrieve_many(self, queries: list[str]) -> list[list[dict[str, Any]]]:
        return [self.retrieve(query) for query in queries]
