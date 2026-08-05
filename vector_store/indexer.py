from typing import Any

from qdrant_client.models import PointStruct
from chunking.chunk_model import CodeChunk
from .qdrant_client import QdrantManager
from .schema import VECTOR_NAME, get_vector_params, get_sparse_vector_params


class VectorIndexer:
    def __init__(self, collection_name: str, embedding_dim: int):
        self.collection_name = collection_name
        self.qdrant = QdrantManager().get_client()
        self._ensure_collection(embedding_dim)

    def _ensure_collection(self, embedding_dim: int):
        existing = [c.name for c in self.qdrant.get_collections().collections]

        if self.collection_name not in existing:
            self.qdrant.create_collection(
                collection_name=self.collection_name,
                vectors_config=get_vector_params(embedding_dim),
                sparse_vectors_config=get_sparse_vector_params(),
            )
            print(f"[VectorIndexer] Created collection: {self.collection_name}")
        else:
            print(f"[VectorIndexer] Collection exists: {self.collection_name}")

    def exists(self, chunk_id: str) -> bool:
        results = self.qdrant.retrieve(
            collection_name=self.collection_name,
            ids=[chunk_id]
        )
        return len(results) > 0

    def index(self, chunks: list[CodeChunk], embeddings: list):
        points = [
            PointStruct(
                id=chunk.chunk_id,
                vector={
                    VECTOR_NAME: list(embedding) if hasattr(embedding, 'tolist') else embedding
                },
                payload={
                    "chunk_id"      : chunk.chunk_id,
                    "repo"          : chunk.repo,
                    "file_path"     : chunk.file_path,
                    "absolute_path" : chunk.absolute_path,
                    "extension"     : chunk.extension,
                    "chunk_source"  : chunk.chunk_source,
                    "language"      : chunk.language,
                    "symbol"        : chunk.symbol,
                    "node_type"     : chunk.node_type,
                    "start_line"    : chunk.start_line,
                    "end_line"      : chunk.end_line,
                    "content"       : chunk.content,
                }
            )
            for chunk, embedding in zip(chunks, embeddings)
        ]

        self.qdrant.upsert(
            collection_name=self.collection_name,
            points=points
        )

        print(f"[VectorIndexer] Indexed {len(points)} chunks")


def chunk_from_payload(payload: dict[str, Any]) -> CodeChunk | None:
    required_keys = [
        "chunk_id", "repo", "file_path", "absolute_path", "extension",
        "chunk_source", "language", "symbol", "node_type",
        "start_line", "end_line", "content",
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
