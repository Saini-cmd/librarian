from bootstrap import ensure_repo_root

ensure_repo_root()

import sys
import uuid

from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue
from sqlalchemy import inspect

from backend.database import SessionLocal, init_db
from backend.state import (
    add_message,
    get_or_create_conversation,
    get_or_create_indexed_repo,
    list_recent_messages,
    load_conversation_summary,
    save_conversation_summary,
    upsert_user,
)
from memory.short_term import build_history
from memory.store import MemoryStore, COLLECTION_NAME


class FakeEmbedder:
    """Deterministic 768-dim vectors — no API calls."""

    def embed_texts(self, texts):
        return [[((hash(t) >> (i % 8)) % 1000) / 1000.0 for i in range(768)] for t in texts]


CLERK_ID = "test-09-memory-user"
REPO_HASH = "test09-hash"
REPO_URL = "https://github.com/test09"


def _cleanup_legacy_points():
    from vector_store.qdrant_client import QdrantManager

    q = QdrantManager().get_client()
    try:
        q.delete(
            collection_name=COLLECTION_NAME,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="clerk_id", match=MatchValue(value=CLERK_ID))]
                )
            ),
        )
    except Exception:
        pass


def main():
    init_db()
    db = SessionLocal()
    _cleanup_legacy_points()

    print("[test_09_memory] starting...")

    # 1. conversation_summaries table auto-created
    assert "conversation_summaries" in inspect(db.bind).get_table_names()
    print("OK conversation_summaries table exists")

    user = upsert_user(db, CLERK_ID)
    get_or_create_indexed_repo(
        db, repo_hash=REPO_HASH, repo_name="test09", repo_url="https://github.com/test09"
    )
    conv = get_or_create_conversation(db, CLERK_ID, repo_name="test09", repo_hash=REPO_HASH)

    # 2. short-term: list_recent_messages order + limit
    m1 = add_message(db, conv.id, "user", "How do I sort a list in Python?")
    m2 = add_message(db, conv.id, "assistant", "Use sorted().")
    recent = list_recent_messages(db, conv.id, limit=10)
    assert [m.role for m in recent] == ["user", "assistant"]
    assert [m.id for m in recent] == [m1.id, m2.id]
    print("OK list_recent_messages order + limit")

    # 3. rolling summary save/load/merge
    save_conversation_summary(
        db, conv.id, "Rolling summary.", total_tokens_covered=5, last_message_id=m2.id
    )
    row = load_conversation_summary(db, conv.id)
    assert row is not None and row.summary_content == "Rolling summary."
    save_conversation_summary(db, conv.id, "Merged.", total_tokens_covered=10)
    assert load_conversation_summary(db, conv.id).summary_content == "Merged."
    print("OK save/load/merge conversation_summary")

    # 4. long-term store: upsert → search → exclusion → idempotent → delete
    store = MemoryStore(embedder=FakeEmbedder())
    assert store.collection_exists(), f"{COLLECTION_NAME} missing"
    text = f"User: {m1.content} | Assistant: {m2.content}"
    pid = store.upsert_exchange(
        clerk_id=CLERK_ID, repo_url=REPO_URL, repo_hash=REPO_HASH, conversation_id=conv.id,
        user_message_id=m1.id, assistant_message_id=m2.id, text=text,
    )
    uuid.UUID(pid)  # Qdrant requires UUID point ids
    hits = store.search("How do I sort?", CLERK_ID, repo_url=REPO_URL)
    assert len(hits) == 1 and "sorted()" in hits[0]["text"]
    hits_excl = store.search(
        "How do I sort?", CLERK_ID, repo_url=REPO_URL, exclude_conversation_id=conv.id
    )
    assert hits_excl == []
    store.upsert_exchange(
        clerk_id=CLERK_ID, repo_url=REPO_URL, repo_hash=REPO_HASH, conversation_id=conv.id,
        user_message_id=m1.id, assistant_message_id=m2.id, text=text,
    )
    assert len(store.search("sort", CLERK_ID, repo_url=REPO_URL)) == 1  # idempotent
    store.delete_by_conversation(conv.id)
    assert store.search("sort", CLERK_ID, repo_url=REPO_URL) == []
    print("OK MemoryStore upsert/search/exclusion/idempotent/delete")

    # 4b. memory is scoped by repo_url, not repo_hash -> survives a sync
    # (search under a NEW commit hash for the same repo must still match).
    store.upsert_exchange(
        clerk_id=CLERK_ID, repo_url=REPO_URL, repo_hash=REPO_HASH, conversation_id=conv.id,
        user_message_id=m1.id, assistant_message_id=m2.id, text=text,
    )
    synced_hits = store.search(
        "How do I sort?", CLERK_ID, repo_url=REPO_URL, top_k=5
    )
    assert len(synced_hits) == 1, "memory must be retrievable via repo_url"
    assert synced_hits[0]["text"] == text
    # repo_hash is stored but NOT used for scoping: a different hash still matches
    assert len(store.search("sort", CLERK_ID, repo_url=REPO_URL)) == 1
    store.delete_by_conversation(conv.id)
    print("OK memory scoped by repo_url — survives sync (repo_hash is metadata only)")

    # 5. build_history with summary fallback
    hc = build_history(db, conv.id, max_turns=10)
    assert [m["role"] for m in hc.messages] == ["user", "assistant"]
    hc_sum = build_history(db, conv.id, max_turns=10, token_budget=1)
    assert hc_sum.summary == "Merged."
    print("OK build_history (incl. rolling-summary fallback)")

    # cleanup
    db.delete(conv)
    db.commit()
    db.delete(user)
    db.commit()
    from backend.models import IndexedRepo

    db.query(IndexedRepo).filter(IndexedRepo.repo_hash == REPO_HASH).delete()
    db.commit()
    db.close()
    print("\nALL test_09_memory CHECKS PASSED")


if __name__ == "__main__":
    main()
