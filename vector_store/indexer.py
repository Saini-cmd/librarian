from typing import Any
import json

from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchAny,
    MatchValue,
    PointStruct,
)
from chunking.chunk_model import CodeChunk
from .qdrant_client import QdrantManager
from .schema import VECTOR_NAME, get_vector_params, get_sparse_vector_params


# Qdrant rejects requests whose JSON payload exceeds 32MB. Batch upserts well
# under that cap (~8MB target) so content-heavy repos don't trip a 400.
_MAX_UPSERT_PAYLOAD_BYTES = 8 * 1024 * 1024
_MAX_UPSERT_POINTS = 500
_POINT_OVERHEAD_BYTES = 128


def _batch_points(points: list[PointStruct]):
    """Yield ``points`` in batches bounded by payload size and point count."""
    batch: list[PointStruct] = []
    batch_bytes = 0
    for point in points:
        point_bytes = len(json.dumps(point.payload, default=str)) + _POINT_OVERHEAD_BYTES
        if batch and (len(batch) >= _MAX_UPSERT_POINTS or batch_bytes + point_bytes > _MAX_UPSERT_PAYLOAD_BYTES):
            yield batch
            batch, batch_bytes = [], 0
        batch.append(point)
        batch_bytes += point_bytes
    if batch:
        yield batch


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
                    "repo_url"      : chunk.repo_url,
                    "repo_hash"     : chunk.repo_hash,
                    "file_path"     : chunk.file_path,
                    "absolute_path" : chunk.absolute_path,
                    "extension"     : chunk.extension,
                    "chunk_source"  : chunk.chunk_source,
                    "language"      : chunk.language,
                    "symbol"        : chunk.symbol,
                    "node_type"     : chunk.node_type,
                    "qualified_name": chunk.qualified_name,
                    "parent_symbol" : chunk.parent_symbol,
                    "start_line"    : chunk.start_line,
                    "end_line"      : chunk.end_line,
                    "content"       : chunk.content,
                }
            )
            for chunk, embedding in zip(chunks, embeddings)
        ]

        total_batches = 0
        for batch in _batch_points(points):
            self.qdrant.upsert(
                collection_name=self.collection_name,
                points=batch,
            )
            total_batches += 1

        print(
            f"[VectorIndexer] Indexed {len(points)} chunks "
            f"(in {total_batches} upsert batch{'es' if total_batches != 1 else ''})"
        )


    def delete_by_repo_hash(
        self,
        repo_hash: str,
        keep_chunk_ids: list[str] | None = None,
    ) -> None:
        """Delete all points for a commit, optionally keeping cited chunk ids.

        Used by sync cleanup: delete an old commit's chunks except those a
        `citation` row still references. repo_hash is globally unique, so the
        commit alone scopes the deletion.
        """
        delete_points_by_repo_hash(repo_hash, keep_chunk_ids, self.collection_name)


def delete_points_by_repo_hash(
    repo_hash: str,
    keep_chunk_ids: list[str] | None = None,
    collection_name: str = "code_chunks",
) -> None:
    """Delete all Qdrant points for a commit (hash-only scoped), keeping cited ids."""
    client = QdrantManager().get_client()
    flt = Filter(must=[FieldCondition(key="repo_hash", match=MatchValue(value=repo_hash))])
    if keep_chunk_ids:
        flt.must_not = [
            FieldCondition(key="chunk_id", match=MatchAny(any=list(keep_chunk_ids)))
        ]

    client.delete(
        collection_name=collection_name,
        points_selector=FilterSelector(filter=flt),
    )
    print(
        f"[VectorIndexer] Deleted chunks for {repo_hash} "
        f"(keeping {len(keep_chunk_ids or [])} cited)"
    )


def scroll_chunks_by_file(
    repo_hash: str,
    file_path: str,
    collection_name: str = "code_chunks",
) -> list[CodeChunk]:
    """Return every chunk for one file in a commit, sorted by line span.

    Chunks tile the file (AST symbols + text gaps), so concatenating them in
    source order reconstructs the full file. Used by the graph panel's
    "complete code" view.
    """
    client = QdrantManager().get_client()
    flt = Filter(
        must=[
            FieldCondition(key="repo_hash", match=MatchValue(value=repo_hash)),
            FieldCondition(key="file_path", match=MatchValue(value=file_path)),
        ]
    )
    chunks: list[CodeChunk] = []
    offset: object | None = None
    while True:
        points, next_offset = client.scroll(
            collection_name=collection_name,
            scroll_filter=flt,
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in points:
            chunk = chunk_from_payload(point.payload)
            if chunk is not None:
                chunks.append(chunk)
        if not next_offset:
            break
        offset = next_offset
    chunks.sort(key=lambda c: (c.start_line, c.end_line))
    return chunks


def chunk_from_payload(payload: dict[str, Any]) -> CodeChunk | None:
    required_keys = [
        "chunk_id", "file_path", "absolute_path", "extension",
        "chunk_source", "language", "symbol", "node_type",
        "start_line", "end_line", "content",
    ]
    if not all(key in payload for key in required_keys):
        return None

    return CodeChunk(
        chunk_id=str(payload["chunk_id"]),
        repo_url=str(payload.get("repo_url") or ""),
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
        repo_hash=payload.get("repo_hash"),
        qualified_name=str(payload.get("qualified_name") or ""),
        parent_symbol=str(payload.get("parent_symbol") or ""),
    )
