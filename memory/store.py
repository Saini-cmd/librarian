"""Long-term memory vector store (Qdrant `long_term_memory` collection).

Stores each user+assistant exchange as a vectorized raw text chunk, scoped by
`clerk_id` (+ `repo_url`). Retrieval embeds a query and filters by
`clerk_id`/`repo_url`, optionally excluding the current conversation so
long-term results don't duplicate short-term history.

Scoping is by `repo_url` (not `repo_hash`): `repo_url` is stable across commits,
so long-term memory survives a sync — after a conversation re-points to a new
commit hash, its memory is still retrievable (and keeps accumulating). The
`repo_hash` at write time is kept in the payload as informational metadata only.
"""

import logging
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
)

from embedding.api_embedder import APIEmbedder
from vector_store.qdrant_client import QdrantManager
from vector_store.schema import VECTOR_NAME, Distance, VectorParams


logger = logging.getLogger(__name__)

COLLECTION_NAME = "long_term_memory"
EMBEDDING_DIM = 768
MEMORY_TYPE_RAW_EXCHANGE = "raw_exchange"

# Fixed namespace so uuid5 point ids are deterministic per exchange (idempotent upserts).
_POINT_ID_NAMESPACE = uuid.UUID("5f0a1c2e-8b3d-4e6a-9c1b-2d3e4f5a6b7c")


@lru_cache(maxsize=1)
def get_memory_store() -> "MemoryStore":
    """Shared store for the request path (real embedder). Tests inject a fake instead."""
    return MemoryStore()


class MemoryStore:
    """Qdrant-backed long-term memory store (embed + upsert + search + delete)."""

    def __init__(self, embedder: APIEmbedder | None = None):
        self.embedder = embedder or APIEmbedder()
        self.client = QdrantManager().get_client()
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        existing = [c.name for c in self.client.get_collections().collections]
        if COLLECTION_NAME in existing:
            return
        self.client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config={
                VECTOR_NAME: VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE)
            },
        )
        logger.info("Created Qdrant collection %s", COLLECTION_NAME)

    def collection_exists(self) -> bool:
        try:
            existing = [c.name for c in self.client.get_collections().collections]
            return COLLECTION_NAME in existing
        except Exception:
            return False

    @staticmethod
    def point_id(conversation_id: Any, user_message_id: Any) -> str:
        """Deterministic UUID point id for one exchange (idempotent upserts)."""
        return str(
            uuid.uuid5(_POINT_ID_NAMESPACE, f"{conversation_id}-{user_message_id}")
        )

    def embed(self, text: str) -> list[float]:
        return self.embedder.embed_texts([text])[0]

    def upsert_exchange(
        self,
        clerk_id: str,
        conversation_id: Any,
        user_message_id: Any,
        text: str,
        repo_url: str | None = None,
        repo_hash: str | None = None,
        assistant_message_id: Any = None,
    ) -> str:
        """Embed and store one exchange. Idempotent via the deterministic point id.

        `repo_url` is the scope (stable across commits); `repo_hash` is stored
        as informational metadata (which commit this exchange was written against).
        """
        vector = self.embed(text)
        point_id = self.point_id(conversation_id, user_message_id)
        self.client.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                PointStruct(
                    id=point_id,
                    vector={VECTOR_NAME: vector},
                    payload={
                        "clerk_id": clerk_id,
                        "repo_url": repo_url,
                        "repo_hash": repo_hash,
                        "conversation_id": str(conversation_id),
                        "memory_type": MEMORY_TYPE_RAW_EXCHANGE,
                        "text": text,
                        "user_message_id": str(user_message_id),
                        "assistant_message_id": (
                            str(assistant_message_id) if assistant_message_id else None
                        ),
                        "created_at": int(datetime.now(timezone.utc).timestamp()),
                    },
                )
            ],
        )
        return point_id

    def search(
        self,
        query_text: str,
        clerk_id: str,
        repo_url: str | None = None,
        exclude_conversation_id: Any = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Return top-K raw memory chunks for a user (optionally repo-scoped).

        Filtering is by `repo_url` so memory survives syncs; the current
        conversation is excluded so long-term results complement (rather than
        duplicate) the short-term history already in the prompt.
        """
        vector = self.embed(query_text)

        must = [FieldCondition(key="clerk_id", match=MatchValue(value=clerk_id))]
        if repo_url:
            must.append(FieldCondition(key="repo_url", match=MatchValue(value=repo_url)))
        flt = Filter(must=must)
        if exclude_conversation_id:
            flt.must_not = [
                FieldCondition(
                    key="conversation_id",
                    match=MatchValue(value=str(exclude_conversation_id)),
                )
            ]

        response = self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,
            using=VECTOR_NAME,
            query_filter=flt,
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )

        results: list[dict[str, Any]] = []
        for rank, point in enumerate(response.points, start=1):
            payload = point.payload or {}
            results.append(
                {
                    "text": payload.get("text", ""),
                    "memory_type": payload.get("memory_type"),
                    "conversation_id": payload.get("conversation_id"),
                    "user_message_id": payload.get("user_message_id"),
                    "score": float(point.score or 0.0),
                    "rank": rank,
                }
            )
        return results

    def delete_by_conversation(self, conversation_id: Any) -> None:
        """Delete every memory point belonging to a conversation."""
        flt = Filter(
            must=[
                FieldCondition(
                    key="conversation_id", match=MatchValue(value=str(conversation_id))
                )
            ]
        )
        self.client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=FilterSelector(filter=flt),
        )
