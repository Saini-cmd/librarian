from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import get_db
from backend.models import UserRepo
from backend.state import upsert_user


router = APIRouter(prefix="/api/repositories", tags=["repositories"])


class RepoOut(BaseModel):
    repo_name: str
    repo_url: str
    files_discovered: int
    chunks_created: int
    status: str
    indexed_at: datetime


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
