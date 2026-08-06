from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import get_db
from backend.models import UserRepo
from backend.state import upsert_user, user_repo_exists
from summarization.summary_store import SummaryStore
from symbol_graph.graph_builder import build_repo_graph


router = APIRouter(prefix="/api/repositories", tags=["repositories"])


class RepoOut(BaseModel):
    repo_name: str
    repo_url: str
    files_discovered: int
    chunks_created: int
    status: str
    indexed_at: datetime


class FileSummaryOut(BaseModel):
    repo_name: str
    file_path: str
    summary: str


@router.get("", response_model=list[RepoOut])
def list_repositories(
    clerk_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RepoOut]:
    user = upsert_user(db, clerk_id)
    repos = (
        db.query(UserRepo)
        .filter(UserRepo.user_id == user.id)
        .order_by(UserRepo.updated_at.desc())
        .all()
    )
    return [
        RepoOut(
            repo_name=repo.repo_name,
            repo_url=repo.repo_url,
            files_discovered=repo.files_discovered,
            chunks_created=repo.chunks_created,
            status=repo.status,
            indexed_at=repo.updated_at,
        )
        for repo in repos
    ]


def _require_repo(db: Session, user_id, repo_name: str) -> None:
    if not user_repo_exists(db, user_id, repo_name):
        raise HTTPException(status_code=404, detail="Repository not found")


@router.get("/{repo_name}/graph")
def repo_graph(
    repo_name: str,
    clerk_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    user = upsert_user(db, clerk_id)
    _require_repo(db, user.id, repo_name)
    return build_repo_graph(repo_name)


@router.get("/{repo_name}/summary", response_model=FileSummaryOut)
def repo_file_summary(
    repo_name: str,
    file_path: str,
    clerk_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileSummaryOut:
    user = upsert_user(db, clerk_id)
    _require_repo(db, user.id, repo_name)
    summary = SummaryStore.get(repo_name, file_path)
    if summary is None:
        raise HTTPException(status_code=404, detail="No summary for this file")
    return FileSummaryOut(repo_name=repo_name, file_path=file_path, summary=summary)
