"""Indexed-repo data access + per-user repo derivation.

Repo identity = normalized `repo_url` + per-commit `repo_hash`; a user's repos
are derived from their conversations (no user↔repo join table).
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.db import SessionLocal
from core.models import Conversation, IndexedRepo


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
