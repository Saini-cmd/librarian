"""Admin data-wipe operations (`POST /api/reset` + `/api/status` collection probe).

Kept in the API layer (not `core/`) because reset is an app-level admin action
that reaches into Qdrant and the chat-memory domain, and the API layer may
depend on domains while `core/` may not.
"""

from sqlalchemy.orm import Session

from core.models import Citation, Conversation, IndexedRepo, RepoGraph
from memory.store import COLLECTION_NAME as MEMORY_COLLECTION_NAME
from vector_store.qdrant_client import QdrantManager


COLLECTION_NAME = "code_chunks"


def collection_exists(collection_name: str = COLLECTION_NAME) -> bool:
    try:
        client = QdrantManager().get_client()
        collections = client.get_collections().collections
        return any(c.name == collection_name for c in collections)
    except Exception:
        return False


def reset_index_state(db: Session, wipe: bool = True) -> None:
    if wipe:
        for name in (COLLECTION_NAME, MEMORY_COLLECTION_NAME):
            try:
                if collection_exists(name):
                    QdrantManager().get_client().delete_collection(name)
            except Exception:
                pass

    # Detach conversations from repos (keep chat history), then wipe repo-scoped data.
    db.query(Conversation).update({Conversation.repo_hash: None})
    db.query(Citation).delete()
    db.query(RepoGraph).delete()
    db.query(IndexedRepo).delete()
    db.commit()
