import logging
from typing import Any

from chunking.chunk_model import CodeChunk
from vector_store.qdrant_client import QdrantManager


logger = logging.getLogger(__name__)


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

    def search(self, query_vector: list[float], top_k: int | None = None) -> list[dict[str, Any]]:
        limit = top_k or self.top_k
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )

        results: list[dict[str, Any]] = []
        for rank, point in enumerate(response.points, start=1):
            payload = point.payload or {}
            chunk = self._chunk_from_payload(payload)
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

    @staticmethod
    def _chunk_from_payload(payload: dict[str, Any]) -> CodeChunk | None:
        required_keys = [
            "chunk_id",
            "repo",
            "file_path",
            "absolute_path",
            "extension",
            "chunk_source",
            "language",
            "symbol",
            "node_type",
            "start_line",
            "end_line",
            "content",
        ]
        if not all(key in payload for key in required_keys):
            return None

        return CodeChunk(
            chunk_id=str(payload["chunk_id"]),
            repo=str(payload["repo"]),
            file_path=str(payload["file_path"]),
            absolute_path=str(payload["absolute_path"]),
            extension=str(payload["extension"]),
            chunk_source=str(payload["chunk_source"]),
            language=str(payload["language"]),
            symbol=str(payload["symbol"]),
            node_type=str(payload["node_type"]),
            start_line=int(payload["start_line"]),
            end_line=int(payload["end_line"]),
            content=str(payload["content"]),
        )
