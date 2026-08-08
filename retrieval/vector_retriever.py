import logging
from typing import Any

from qdrant_client.models import FieldCondition, Filter, MatchValue

from vector_store.indexer import chunk_from_payload
from vector_store.qdrant_client import QdrantManager
from vector_store.schema import VECTOR_NAME


logger = logging.getLogger(__name__)


def _repo_hash_filter(repo_hash: str | None = None) -> Filter | None:
    if not repo_hash:
        return None
    return Filter(must=[FieldCondition(key="repo_hash", match=MatchValue(value=repo_hash))])


class VectorRetriever:
    """Retrieves candidate chunks from Qdrant using dense vector similarity."""

    def __init__(self, collection_name: str = "code_chunks", top_k: int = 20):
        self.collection_name = collection_name
        self.top_k = top_k
        self.client = QdrantManager().get_client()
        logger.info(
            "Initialized VectorRetriever(collection=%s, top_k=%d)",
            collection_name,
            top_k,
        )

    def search(
        self,
        query_vector: list[float],
        top_k: int | None = None,
        repo_hash: str | None = None,
    ) -> list[dict[str, Any]]:
        limit = top_k or self.top_k
        query_filter = _repo_hash_filter(repo_hash)
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            using=VECTOR_NAME,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )

        results: list[dict[str, Any]] = []
        for rank, point in enumerate(response.points, start=1):
            payload = point.payload or {}
            chunk = chunk_from_payload(payload)
            if chunk is None:
                continue

            results.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "chunk": chunk,
                    "score": float(point.score or 0.0),
                    "rank": rank,
                    "source": "vector",
                }
            )

        logger.info("Vector retrieval returned %d results", len(results))
        return results
