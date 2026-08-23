"""Conversation, message, citation, and rolling-summary data access."""

from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.models import Citation, Conversation, ConversationSummary, Message
from core.repositories.indexed_repo import indexed_repo_by_hash


def default_conversation_title(repo_name: str | None = None) -> str:
    ts = datetime.now().strftime("%b %d, %H:%M:%S")
    return f"{repo_name} · {ts}" if repo_name else f"Chat · {ts}"


def resolve_conversation_repo(
    db: Session,
    clerk_id: str,
    conversation_id: Any,
    requested_repo_hash: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Resolve (repo_hash, repo_name, repo_url) a chat should search over.

    Precedence: the conversation's stored repo > the repo the client requested
    (by its commit hash) > None.
    """
    if conversation_id is not None:
        conv = db.get(Conversation, conversation_id)
        if conv is not None and conv.clerk_id == clerk_id and conv.indexed_repo is not None:
            return (
                conv.repo_hash,
                conv.indexed_repo.repo_name,
                conv.indexed_repo.repo_url,
            )
    if requested_repo_hash:
        repo = indexed_repo_by_hash(db, requested_repo_hash)
        if repo is not None and repo.status != "deleted":
            return repo.repo_hash, repo.repo_name, repo.repo_url
    return None, None, None


def get_or_create_conversation(
    db: Session,
    clerk_id: str,
    conversation_id: Any = None,
    title: str | None = None,
    repo_hash: str | None = None,
    repo_name: str | None = None,
) -> Conversation:
    if conversation_id is not None:
        conv = db.get(Conversation, conversation_id)
        if conv is not None and conv.clerk_id == clerk_id:
            return conv
    conv = Conversation(
        clerk_id=clerk_id,
        title=title or default_conversation_title(repo_name),
        repo_hash=repo_hash,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def add_message(
    db: Session,
    conversation_id: Any,
    role: str,
    content: str,
    citation: list[dict] | None = None,
    repo_hash: str | None = None,
) -> Message:
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        citation=citation or [],
        repo_hash=repo_hash,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def list_recent_messages(db: Session, conversation_id: Any, limit: int = 10) -> list[Message]:
    """The `limit` most recent messages of a conversation, oldest first."""
    rows = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    return rows


def messages_since(
    db: Session,
    conversation_id: Any,
    after_message_id: Any = None,
    limit: int = 200,
) -> list[Message]:
    """Messages of a conversation strictly after `after_message_id`, oldest first.

    Orders by `(created_at, id)` so the watermark is a stable resume point even
    when messages share a timestamp. `after_message_id=None` returns all messages.
    """
    query = db.query(Message).filter(Message.conversation_id == conversation_id)
    if after_message_id is not None:
        anchor = db.get(Message, after_message_id)
        if anchor is not None:
            query = query.filter(
                or_(
                    Message.created_at > anchor.created_at,
                    and_(
                        Message.created_at == anchor.created_at,
                        Message.id > anchor.id,
                    ),
                )
            )
    return (
        query.order_by(Message.created_at.asc(), Message.id.asc()).limit(limit).all()
    )


# ---- Conversation summaries (rolling memory) ----


def load_conversation_summary(
    db: Session, conversation_id: Any
) -> ConversationSummary | None:
    return (
        db.query(ConversationSummary)
        .filter(ConversationSummary.conversation_id == conversation_id)
        .first()
    )


def save_conversation_summary(
    db: Session,
    conversation_id: Any,
    summary_content: str,
    total_tokens_covered: int = 0,
    last_message_id: Any = None,
) -> ConversationSummary:
    """Create or merge the rolling summary row for a conversation."""
    row = load_conversation_summary(db, conversation_id)
    if row is None:
        row = ConversationSummary(
            conversation_id=conversation_id,
            summary_content=summary_content,
            total_tokens_covered=total_tokens_covered,
            last_message_id=last_message_id,
        )
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            # Concurrent rollup for the same conversation won the INSERT — merge into it.
            db.rollback()
            row = load_conversation_summary(db, conversation_id)
            if row is None:
                raise
            row.summary_content = summary_content
            row.total_tokens_covered = total_tokens_covered
            row.last_message_id = last_message_id
            db.commit()
    else:
        row.summary_content = summary_content
        row.total_tokens_covered = total_tokens_covered
        row.last_message_id = last_message_id
    db.commit()
    db.refresh(row)
    return row


def write_citations(db: Session, message_id: Any, citations: list[dict]) -> int:
    """Persist durable citation rows (for cleanup + retention). Skips entries without a repo_hash."""
    rows = [
        Citation(
            message_id=message_id,
            citation_id=c["citation_id"],
            repo_hash=c.get("repo_hash"),
            chunk_id=c["chunk_id"],
            file_path=c["file_path"],
            start_line=c["start_line"],
            end_line=c["end_line"],
            symbol=c.get("symbol"),
            language=c.get("language"),
        )
        for c in citations
        if c.get("repo_hash")
    ]
    if rows:
        db.add_all(rows)
        db.commit()
    return len(rows)


def cited_chunk_ids(db: Session, repo_hash: str) -> list[str]:
    """Chunk ids that still have durable citations for a commit (retained during cleanup)."""
    rows = (
        db.query(Citation.chunk_id)
        .filter(Citation.repo_hash == repo_hash)
        .distinct()
        .all()
    )
    return [r[0] for r in rows]
