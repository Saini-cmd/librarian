from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models import (
    Citation,
    Conversation,
    ConversationSummary,
    IndexedRepo,
    Message,
    RepoGraph,
    User,
)
from memory.store import COLLECTION_NAME as MEMORY_COLLECTION_NAME
from vector_store.qdrant_client import QdrantManager


COLLECTION_NAME = "code_chunks"


def normalize_repo_url(repo_url: str) -> str:
    """Canonicalize a repo URL into a single identity form.

    Handles scp-style (git@host:owner/repo.git), ssh://, and http(s);
    strips trailing '.git' and '/'; lowercases the host. This is the single
    place that knows about URL forms — the canonical value is threaded
    through probing, cloning, storage, and lookups.
    """
    url = repo_url.strip()
    if not url:
        return ""

    if "://" not in url and "@" in url and ":" in url:
        host, _, path = url.partition(":")
        url = f"https://{host.removeprefix('git@')}/{path}"

    parsed = urlparse(url)
    scheme = "https" if parsed.scheme in ("", "ssh") else parsed.scheme
    host = parsed.hostname or ""
    path = parsed.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return f"{scheme}://{host}{path}"


def default_conversation_title(repo_name: str | None = None) -> str:
    ts = datetime.now().strftime("%b %d, %H:%M:%S")
    return f"{repo_name} · {ts}" if repo_name else f"Chat · {ts}"


def collection_exists(collection_name: str = COLLECTION_NAME) -> bool:
    try:
        client = QdrantManager().get_client()
        collections = client.get_collections().collections
        return any(c.name == collection_name for c in collections)
    except Exception:
        return False


# ---- Users ----


def get_user_by_clerk_id(db: Session, clerk_id: str) -> User | None:
    return db.query(User).filter(User.clerk_id == clerk_id).first()


def upsert_user(db: Session, clerk_id: str, **fields: Any) -> User:
    user = get_user_by_clerk_id(db, clerk_id)
    if user is None:
        user = User(clerk_id=clerk_id, **fields)
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            # Concurrent first-upsert for the same clerk_id: the other request
            # won the INSERT. Roll back and adopt its row instead of 500ing.
            db.rollback()
            user = get_user_by_clerk_id(db, clerk_id)
            if user is None:
                raise
            for key, value in fields.items():
                setattr(user, key, value)
            db.commit()
    else:
        for key, value in fields.items():
            setattr(user, key, value)
        db.commit()
    db.refresh(user)
    return user


# ---- Indexed repos ----


def get_or_create_indexed_repo(
    db: Session,
    repo_hash: str,
    repo_name: str,
    repo_url: str,
    file_count: int = 0,
    chunks_count: int = 0,
    status: str = "indexed",
) -> IndexedRepo:
    repo = db.query(IndexedRepo).filter(IndexedRepo.repo_hash == repo_hash).first()
    if repo is None:
        repo = IndexedRepo(
            repo_hash=repo_hash,
            repo_name=repo_name,
            repo_url=repo_url,
            file_count=file_count,
            chunks_count=chunks_count,
            status=status,
        )
        db.add(repo)
        try:
            db.commit()
        except IntegrityError:
            # Another pipeline indexed the same commit first — adopt its row
            # (do not overwrite: the winner may still be mid-ingest, status
            # 'indexing', and counts are finalized when its pipeline lands).
            db.rollback()
            repo = db.query(IndexedRepo).filter(IndexedRepo.repo_hash == repo_hash).first()
            if repo is None:
                raise
    else:
        repo.repo_name = repo_name
        repo.repo_url = repo_url
        repo.file_count = file_count
        repo.chunks_count = chunks_count
        repo.status = status
    db.commit()
    db.refresh(repo)
    return repo


def indexed_repo_by_hash(db: Session, repo_hash: str) -> IndexedRepo | None:
    return db.query(IndexedRepo).filter(IndexedRepo.repo_hash == repo_hash).first()


def ensure_repo_indexing(repo_hash: str, repo_name: str, repo_url: str) -> None:
    """Create the indexed_repo row (status='indexing') before any per-commit
    artifacts (file_summary, repo_graph) reference it. Finalized by the caller
    with get_or_create_indexed_repo(..., status='indexed') after the pipeline."""
    db = SessionLocal()
    try:
        if db.query(IndexedRepo).filter(IndexedRepo.repo_hash == repo_hash).first() is None:
            try:
                db.add(
                    IndexedRepo(
                        repo_hash=repo_hash,
                        repo_name=repo_name,
                        repo_url=repo_url,
                        status="indexing",
                    )
                )
                db.commit()
            except IntegrityError:
                # Concurrent pipeline already created the 'indexing' row.
                db.rollback()
    finally:
        db.close()


def mark_repo_failed(repo_hash: str) -> None:
    """Flip a mid-ingest indexed_repo row to 'failed' when the pipeline errors."""
    db = SessionLocal()
    try:
        repo = db.query(IndexedRepo).filter(IndexedRepo.repo_hash == repo_hash).first()
        if repo is not None and repo.status == "indexing":
            repo.status = "failed"
            db.commit()
    finally:
        db.close()


def latest_indexed_repo_by_url(db: Session, repo_url: str) -> IndexedRepo | None:
    return (
        db.query(IndexedRepo)
        .filter(
            IndexedRepo.repo_url == repo_url,
            IndexedRepo.status != "deleted",
        )
        .order_by(IndexedRepo.created_at.desc())
        .first()
    )


# ---- User repo derivation (a user's repos = distinct repos from their conversations) ----


def user_repo_urls(db: Session, clerk_id: str) -> list[str]:
    rows = (
        db.query(IndexedRepo.repo_url)
        .join(Conversation, Conversation.repo_hash == IndexedRepo.repo_hash)
        .filter(Conversation.clerk_id == clerk_id, IndexedRepo.status != "deleted")
        .distinct()
        .all()
    )
    return [r[0] for r in rows]


def user_repo_exists(db: Session, clerk_id: str, repo_url: str) -> bool:
    return repo_url in user_repo_urls(db, clerk_id)


def last_indexed_repo_for_user(db: Session, clerk_id: str) -> str | None:
    conv = (
        db.query(Conversation)
        .filter(Conversation.clerk_id == clerk_id, Conversation.repo_hash.isnot(None))
        .order_by(Conversation.updated_at.desc())
        .first()
    )
    if conv is None or conv.indexed_repo is None:
        return None
    return conv.indexed_repo.repo_name


def list_user_repos(db: Session, clerk_id: str) -> list[IndexedRepo]:
    """One row per repo (the commit the user is most recently active on), most recent first.

    Collapses multiple indexed commits of the same repo_url into a single entry
    so the repos list shows one repo, not one row per commit.
    """
    rows = (
        db.query(IndexedRepo)
        .join(Conversation, Conversation.repo_hash == IndexedRepo.repo_hash)
        .filter(Conversation.clerk_id == clerk_id, IndexedRepo.status != "deleted")
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    seen: dict[str, IndexedRepo] = {}
    for repo in rows:
        if repo.repo_url not in seen:
            seen[repo.repo_url] = repo
    return list(seen.values())


# ---- Conversations ----


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


# ---- Repo graphs ----


def save_repo_graph(db: Session, repo_hash: str, graph: dict) -> None:
    row = db.query(RepoGraph).filter(RepoGraph.repo_hash == repo_hash).first()
    if row is None:
        row = RepoGraph(repo_hash=repo_hash, graph_json=graph)
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            # Concurrent graph save for the same commit won the INSERT — merge into it.
            db.rollback()
            row = db.query(RepoGraph).filter(RepoGraph.repo_hash == repo_hash).first()
            if row is not None:
                row.graph_json = graph
                db.commit()
    else:
        row.graph_json = graph
        db.commit()


def load_repo_graph(db: Session, repo_hash: str) -> dict | None:
    row = db.query(RepoGraph).filter(RepoGraph.repo_hash == repo_hash).first()
    return row.graph_json if row is not None else None


def delete_all_repo_graphs(db: Session) -> None:
    db.query(RepoGraph).delete()
    db.commit()


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
