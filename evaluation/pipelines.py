"""
S1-S4 pipeline setups, composed from the existing retrieval components.

Each setup returns a ranked list of chunk result dicts with the same shape the
answer generator and metrics layer consume: ``chunk``, ``score``, ``rrf_score``,
``vector_score``, ``bm25_score``.

- S1 — naive (fixed-size token) chunks, pure dense vector search
- S2 — AST chunks, pure dense vector search
- S3 — AST chunks, dense vector + BM25 fused with RRF (post-processed)
- S4 — S3 + cross-encoder rerank (the production pipeline, exactly as
  ``RetrievalPipeline`` runs it)

S1/S2 are pure vector baselines (no score shaping); S3/S4 apply the production
post-retrieval score boosting/dedup so the rerank effect (S4 - S3) is measured
on the real production path.
"""

import logging
from dataclasses import dataclass
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

EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
RERANK_MODEL = "cohere/rerank-4-fast"


@dataclass(frozen=True)
class Setup:
    name: str
    description: str
    collection: str


def build_setup_metadata(
    naive_collection: str, ast_collection: str
) -> dict[str, Setup]:
    """Describe the four setups for a given collection pair."""
    return {
        "S1": Setup("S1", "Naive token chunks + dense vector search", naive_collection),
        "S2": Setup("S2", "AST chunks + dense vector search", ast_collection),
        "S3": Setup("S3", "AST chunks + vector + BM25 (RRF fusion)", ast_collection),
        "S4": Setup("S4", "S3 + cross-encoder rerank (production)", ast_collection),
    }


class EvalPipelines:
    """Composes and runs the S1-S4 retrieval setups."""

    def __init__(
        self,
        naive_collection: str,
        ast_collection: str,
        vector_top_k: int = 20,
        bm25_top_k: int = 20,
        rrf_k: int = 60,
        rrf_top_k: int = 30,
        final_top_k: int = 8,
        embedder: APIEmbedder | None = None,
        reranker: OpenRouterReranker | None = None,
    ):
        self.naive_collection = naive_collection
        self.ast_collection = ast_collection
        self.vector_top_k = vector_top_k
        self.bm25_top_k = bm25_top_k
        self.rrf_k = rrf_k
        self.rrf_top_k = rrf_top_k
        self.final_top_k = final_top_k

        self.query_expander = QueryExpander()
        self.embedder = embedder or APIEmbedder(model=EMBEDDING_MODEL)
        self.reranker = reranker or OpenRouterReranker(model=RERANK_MODEL)
        self.post_processor = PostRetrievalProcessor()

        self.vector_naive = VectorRetriever(
            collection_name=naive_collection, top_k=vector_top_k
        )
        self.vector_ast = VectorRetriever(
            collection_name=ast_collection, top_k=vector_top_k
        )
        self.bm25_ast = BM25Index(collection_name=ast_collection, top_k=bm25_top_k)
        self.hybrid = HybridRetriever(
            vector_retriever=self.vector_ast,
            bm25_index=self.bm25_ast,
            vector_top_k=vector_top_k,
            bm25_top_k=bm25_top_k,
            rrf_k=rrf_k,
            rrf_top_k=rrf_top_k,
        )

    def retrieve(
        self,
        setup: str,
        query: str,
        repo_hash: str | None = None,
    ) -> list[dict[str, Any]]:
        if setup == "S1":
            return self._retrieve_vector(self.vector_naive, query, repo_hash)
        if setup == "S2":
            return self._retrieve_vector(self.vector_ast, query, repo_hash)
        if setup == "S3":
            return self._retrieve_hybrid(query, repo_hash, rerank=False)
        if setup == "S4":
            return self._retrieve_hybrid(query, repo_hash, rerank=True)
        raise ValueError(f"unknown setup: {setup}")

    def _retrieve_vector(
        self,
        retriever: VectorRetriever,
        query: str,
        repo_hash: str | None,
    ) -> list[dict[str, Any]]:
        expanded = self.query_expander.expand(query)
        query_vector = self.embedder.embed_query(expanded)
        results = retriever.search(query_vector, top_k=self.vector_top_k, repo_hash=repo_hash)

        return [
            {
                "chunk": item["chunk"],
                "score": float(item["score"]),
                "rrf_score": None,
                "vector_score": float(item["score"]),
                "bm25_score": None,
            }
            for item in results[: self.final_top_k]
        ]

    def _retrieve_hybrid(
        self,
        query: str,
        repo_hash: str | None,
        rerank: bool,
    ) -> list[dict[str, Any]]:
        expanded = self.query_expander.expand(query)
        query_vector = self.embedder.embed_query(expanded)

        merged = self.hybrid.retrieve(
            query=expanded,
            query_vector=query_vector,
            repo_hash=repo_hash,
        )
        adjusted = self.post_processor.adjust_scores(merged.candidates)
        deduped = self.post_processor.dedupe_candidates(adjusted)

        if not rerank:
            return [self._to_result_dict(c) for c in deduped[: self.final_top_k]]

        try:
            reranked = self.reranker.rerank(
                query=query,
                candidates=deduped,
                top_k=max(self.final_top_k * 3, self.final_top_k),
            )
            results = self.post_processor.dedupe_reranked(reranked, top_k=self.final_top_k)
            for item in results:
                item["reranked"] = True
        except Exception:
            logger.warning("stage=rerank_failed falling_back_to_hybrid", exc_info=True)
            results = [self._to_result_dict(c) for c in deduped[: self.final_top_k]]
            for item in results:
                item["reranked"] = False
        return results

    @staticmethod
    def _to_result_dict(candidate: HybridCandidate) -> dict[str, Any]:
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
