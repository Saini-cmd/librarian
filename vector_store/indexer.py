from qdrant_client.models import PointStruct
from chunking.chunk_model import CodeChunk
from .qdrant_client import QdrantManager
from .schema import get_vector_params

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
                vectors_config=get_vector_params(embedding_dim)
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
                vector=embedding.tolist(),
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