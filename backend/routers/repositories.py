from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import get_db
from backend.models import UserRepo
from backend.state import (
    COLLECTION_NAME,
    load_repo_graph,
    save_repo_graph,
    upsert_user,
    user_repo_exists,
)
from summarization.summary_store import SummaryStore
from symbol_graph.graph_builder import build_repo_graph
from vector_store.indexer import chunk_from_payload
from vector_store.qdrant_client import QdrantManager


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


class ChunkOut(BaseModel):
    chunk_id: str
    repo: str
    file_path: str
    absolute_path: str
    extension: str
    chunk_source: str
    language: str
    symbol: str
    node_type: str
    start_line: int
    end_line: int
    content: str


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
    graph = load_repo_graph(db, repo_name)
    if graph is None:
        graph = build_repo_graph(repo_name)
        save_repo_graph(db, repo_name, graph)
    return graph


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


@router.get("/{repo_name}/chunks/{chunk_id}", response_model=ChunkOut)
def repo_chunk(
    repo_name: str,
    chunk_id: str,
    clerk_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChunkOut:
    user = upsert_user(db, clerk_id)
    _require_repo(db, user.id, repo_name)

    try:
        points = QdrantManager().get_client().retrieve(
            collection_name=COLLECTION_NAME,
            ids=[chunk_id],
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to read chunk store")

    if not points:
        raise HTTPException(status_code=404, detail="Chunk not found")

    chunk = chunk_from_payload(points[0].payload)
    if chunk is None or chunk.repo != repo_name:
        raise HTTPException(status_code=404, detail="Chunk not found")

    return ChunkOut(**vars(chunk))
