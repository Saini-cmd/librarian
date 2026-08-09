import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import get_db
from backend.models import Conversation, Message
from backend.state import (
    default_conversation_title,
    latest_indexed_repo_by_url,
    normalize_repo_url,
    upsert_user,
)
from memory.store import get_memory_store


router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class ConversationCreate(BaseModel):
    title: str | None = None
    repo_name: str | None = None
    repo_url: str | None = None


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    citations: list[dict] = []
    repo_hash: str | None = None
    created_at: datetime


class ConversationOut(BaseModel):
    id: str
    title: str
    repo_name: str | None = None
    repo_url: str | None = None
    repo_hash: str | None = None
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = []


def _to_out(conv: Conversation) -> ConversationOut:
    repo = conv.indexed_repo
    return ConversationOut(
        id=str(conv.id),
        title=conv.title,
        repo_name=repo.repo_name if repo else None,
        repo_url=repo.repo_url if repo else None,
        repo_hash=repo.repo_hash if repo else None,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


def _require_owned(db: Session, clerk_id: str, conversation_id: uuid.UUID) -> Conversation:
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.clerk_id != clerk_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.get("", response_model=list[ConversationOut])
def list_conversations(
    clerk_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ConversationOut]:
    user = upsert_user(db, clerk_id)
    convs = (
        db.query(Conversation)
        .filter(Conversation.clerk_id == user.clerk_id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    return [_to_out(conv) for conv in convs]


@router.post("", response_model=ConversationOut, status_code=201)
def create_conversation(
    payload: ConversationCreate,
    clerk_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationOut:
    user = upsert_user(db, clerk_id)
    repo_hash = None
    if payload.repo_url:
        repo = latest_indexed_repo_by_url(db, normalize_repo_url(payload.repo_url))
        repo_hash = repo.repo_hash if repo else None
    conv = Conversation(
        clerk_id=user.clerk_id,
        title=payload.title or default_conversation_title(payload.repo_name),
        repo_hash=repo_hash,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return _to_out(conv)


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: uuid.UUID,
    clerk_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationDetail:
    user = upsert_user(db, clerk_id)
    conv = _require_owned(db, user.clerk_id, conversation_id)
    return ConversationDetail(
        **_to_out(conv).model_dump(),
        messages=[
            MessageOut(
                id=str(m.id),
                role=m.role,
                content=m.content,
                citations=m.citation or [],
                repo_hash=m.repo_hash,
                created_at=m.created_at,
            )
            for m in conv.messages
        ],
    )


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: uuid.UUID,
    clerk_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    user = upsert_user(db, clerk_id)
    conv = _require_owned(db, user.clerk_id, conversation_id)
    db.delete(conv)  # cascades messages + citation + conversation_summaries
    db.commit()
    # Purge long-term memory points for this conversation (best-effort — Qdrant down
    # must not block the deletion).
    try:
        get_memory_store().delete_by_conversation(conversation_id)
    except Exception:
        pass
