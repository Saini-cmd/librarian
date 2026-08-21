import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from backend.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    clerk_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class IndexedRepo(Base):
    __tablename__ = "indexed_repo"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    repo_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    repo_name: Mapped[str] = mapped_column(String(255), index=True)
    repo_url: Mapped[str] = mapped_column(String(2048))
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    chunks_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="indexed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    file_summaries: Mapped[list["FileSummary"]] = relationship(
        back_populates="indexed_repo", cascade="all, delete-orphan"
    )
    graphs: Mapped[list["RepoGraph"]] = relationship(
        back_populates="indexed_repo", cascade="all, delete-orphan"
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="indexed_repo"
    )


class FileSummary(Base):
    __tablename__ = "file_summary"
    __table_args__ = (UniqueConstraint("repo_hash", "file_path", name="uq_repo_file_summary"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    repo_hash: Mapped[str] = mapped_column(
        String(64), ForeignKey("indexed_repo.repo_hash", ondelete="CASCADE"), index=True
    )
    file_path: Mapped[str] = mapped_column(String(1024))
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    indexed_repo: Mapped["IndexedRepo"] = relationship(back_populates="file_summaries")


class RepoGraph(Base):
    __tablename__ = "repo_graph"
    __table_args__ = (UniqueConstraint("repo_hash", name="uq_repo_graph_repo_hash"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    repo_hash: Mapped[str] = mapped_column(
        String(64), ForeignKey("indexed_repo.repo_hash", ondelete="CASCADE"), index=True
    )
    build_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    graph_json: Mapped[dict] = mapped_column(JSON)

    indexed_repo: Mapped["IndexedRepo"] = relationship(back_populates="graphs")

class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    clerk_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("users.clerk_id", ondelete="CASCADE"), index=True
    )
    repo_hash: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("indexed_repo.repo_hash"), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(500), default="New chat")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    user: Mapped["User"] = relationship(back_populates="conversations")
    indexed_repo: Mapped["IndexedRepo | None"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )
    summary: Mapped["ConversationSummary | None"] = relationship(
        back_populates="conversation",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    citation: Mapped[list[dict]] = mapped_column(JSON, default=list)
    repo_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    citations: Mapped[list["Citation"]] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )


class Citation(Base):
    __tablename__ = "citation"
    __table_args__ = (
        UniqueConstraint("message_id", "citation_id", name="uq_message_citation"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    citation_id: Mapped[str] = mapped_column(String(16))
    repo_hash: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("indexed_repo.repo_hash", ondelete="RESTRICT"), index=True, nullable=True
    )
    chunk_id: Mapped[str] = mapped_column(String(64), index=True)
    file_path: Mapped[str] = mapped_column(String(1024))
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    symbol: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    message: Mapped["Message"] = relationship(back_populates="citations")


class ConversationSummary(Base):
    """Rolling per-conversation summary, maintained by the background summarizer.

    `last_message_id` is the watermark: the summarizer merges messages created
    after it into `summary_content`. One row per conversation.
    """

    __tablename__ = "conversation_summaries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), unique=True, index=True
    )
    summary_content: Mapped[str] = mapped_column(Text)
    total_tokens_covered: Mapped[int] = mapped_column(Integer, default=0)
    last_message_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="summary")


class UsageEvent(Base):
    """One recorded cost-bearing action (per user), for the 24h usage cap.

    Append-only: ``record_usage`` inserts a row per action the user actually
    spent API budget on; ``check_usage`` counts rows newer than the window. The
    composite index serves the exact count query
    ``WHERE clerk_id = ? AND action IN (...) AND created_at >= ?``.
    """

    __tablename__ = "usage_events"
    __table_args__ = (
        Index("ix_usage_events_clerk_action_time", "clerk_id", "action", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    clerk_id: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
