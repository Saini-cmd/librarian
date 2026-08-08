import json
import logging
import threading
from datetime import datetime
from queue import Empty, Queue

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import SessionLocal, get_db
from backend.models import Conversation, FileSummary, IndexedRepo, RepoGraph
from backend.state import (
    COLLECTION_NAME,
    cited_chunk_ids,
    get_or_create_indexed_repo,
    indexed_repo_by_hash,
    list_user_repos,
    load_repo_graph,
    save_repo_graph,
    upsert_user,
    user_repo_exists,
)
from ingestion.github_api_fetcher import GitHubAPIFetcher
from orchestration.orchestrator import Orchestrator
from rag.llm_client import LLMClient
from rag.types import LLMConfig
from summarization.summary_store import SummaryStore
from symbol_graph.graph_builder import build_repo_graph
from vector_store.indexer import (
    chunk_from_payload,
    delete_points_by_repo_hash,
    scroll_chunks_by_file,
)
from vector_store.qdrant_client import QdrantManager


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/repositories", tags=["repositories"])


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _sse_response(events: list[dict]) -> StreamingResponse:
    def gen():
        for event in events:
            yield _sse(event)

    return StreamingResponse(gen(), media_type="text/event-stream")


class RepoOut(BaseModel):
    repo_name: str
    repo_url: str
    repo_hash: str
    files_discovered: int
    chunks_created: int
    status: str
    indexed_at: datetime


class FileSummaryOut(BaseModel):
    repo_name: str
    repo_hash: str
    file_path: str
    summary: str


class ChunkOut(BaseModel):
    chunk_id: str
    repo_url: str
    repo_hash: str | None = None
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


class ExplainRequest(BaseModel):
    file_path: str
    kind: str = "entity"
    label: str = ""
    start_line: int | None = None
    end_line: int | None = None
    code: str


class UpdatesOut(BaseModel):
    repo_hash: str
    updates_available: bool
    remote_hash: str | None = None


def _require_repo_by_hash(db: Session, clerk_id: str, repo_hash: str) -> IndexedRepo:
    repo = indexed_repo_by_hash(db, repo_hash)
    if repo is None or repo.status == "deleted":
        raise HTTPException(status_code=404, detail="Repository not found")
    if not user_repo_exists(db, clerk_id, repo.repo_url):
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo


def _repo_out(repo: IndexedRepo) -> RepoOut:
    return RepoOut(
        repo_name=repo.repo_name,
        repo_url=repo.repo_url,
        repo_hash=repo.repo_hash,
        files_discovered=repo.file_count,
        chunks_created=repo.chunks_count,
        status=repo.status,
        indexed_at=repo.updated_at,
    )


@router.get("", response_model=list[RepoOut])
def list_repositories(
    clerk_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RepoOut]:
    user = upsert_user(db, clerk_id)
    return [_repo_out(repo) for repo in list_user_repos(db, user.clerk_id)]


@router.get("/{repo_hash}/graph")
def repo_graph(
    repo_hash: str,
    clerk_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    user = upsert_user(db, clerk_id)
    repo = _require_repo_by_hash(db, user.clerk_id, repo_hash)
    graph = load_repo_graph(db, repo.repo_hash)
    if graph is None:
        graph = build_repo_graph(repo.repo_hash, repo_label=repo.repo_name)
        save_repo_graph(db, repo.repo_hash, graph)
    return graph


@router.get("/{repo_hash}/summary", response_model=FileSummaryOut)
def repo_file_summary(
    repo_hash: str,
    file_path: str,
    clerk_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileSummaryOut:
    user = upsert_user(db, clerk_id)
    repo = _require_repo_by_hash(db, user.clerk_id, repo_hash)
    summary = SummaryStore.get(repo.repo_hash, file_path)
    if summary is None:
        raise HTTPException(status_code=404, detail="No summary for this file")
    return FileSummaryOut(
        repo_name=repo.repo_name,
        repo_hash=repo.repo_hash,
        file_path=file_path,
        summary=summary,
    )


@router.get("/{repo_hash}/chunks", response_model=list[ChunkOut])
def repo_file_chunks(
    repo_hash: str,
    file_path: str,
    clerk_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ChunkOut]:
    """All chunks for one file in a commit, sorted by line span (line coverage
    tiles the file, so the frontend reconstructs the full source from them)."""
    user = upsert_user(db, clerk_id)
    repo = _require_repo_by_hash(db, user.clerk_id, repo_hash)
    try:
        chunks = scroll_chunks_by_file(repo.repo_hash, file_path)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to read chunk store")
    return [ChunkOut(**vars(c)) for c in chunks]


@router.get("/{repo_hash}/chunks/{chunk_id}", response_model=ChunkOut)
def repo_chunk(
    repo_hash: str,
    chunk_id: str,
    clerk_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChunkOut:
    user = upsert_user(db, clerk_id)
    repo = indexed_repo_by_hash(db, repo_hash)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    if not user_repo_exists(db, user.clerk_id, repo.repo_url):
        raise HTTPException(status_code=404, detail="Repository not found")
    # Deleted (tombstoned) commits are intentionally allowed here: their cited
    # chunks are retained in Qdrant precisely so historical citations stay
    # clickable after a sync.

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
    if chunk is None or chunk.repo_hash != repo.repo_hash:
        raise HTTPException(status_code=404, detail="Chunk not found")

    return ChunkOut(**vars(chunk))


EXPLAIN_SYSTEM_PROMPT = (
    "You are a senior software engineer explaining a single code node. "
    "Explain it clearly and concisely in markdown: what the code does, how it "
    "works, its inputs/outputs, and any notable patterns, edge cases, or "
    "pitfalls. Stay grounded in the provided code — do not invent behavior, "
    "APIs, or files that are not present. Keep the explanation under 500 words."
)


@router.post("/{repo_hash}/explain")
def explain_node(
    repo_hash: str,
    payload: ExplainRequest,
    clerk_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream an LLM explanation of a code node (graph panel Explain button).

    Stateless: no messages/citations persisted. The client sends the node's
    code (assembled file source for files, the snippet for entities) plus
    metadata; tokens stream over SSE until a final `done` event.
    """
    user = upsert_user(db, clerk_id)
    repo = _require_repo_by_hash(db, user.clerk_id, repo_hash)
    llm_client = LLMClient(config=LLMConfig(max_tokens=700))
    loc = f" lines {payload.start_line}-{payload.end_line}" if payload.start_line else ""
    user_prompt = (
        f"Code node: {payload.label or payload.kind} ({payload.kind})\n"
        f"File: {payload.file_path}{loc}\n\n"
        f"```\n{payload.code}\n```\n\n"
        "Explain this code."
    )
    messages = [
        {"role": "system", "content": EXPLAIN_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    def event_stream():
        try:
            for token in llm_client.stream_generate(messages):
                yield f"data: {json.dumps({'token': token})}\n\n"
        except Exception as exc:
            logger.exception("Explain failed for %s", payload.file_path)
            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
        finally:
            db.close()
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/{repo_hash}/updates", response_model=UpdatesOut)
def repo_updates(
    repo_hash: str,
    clerk_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UpdatesOut:
    user = upsert_user(db, clerk_id)
    repo = _require_repo_by_hash(db, user.clerk_id, repo_hash)
    try:
        remote_hash = GitHubAPIFetcher().remote_head_sha(repo.repo_url)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to probe remote repository: {exc}")
    return UpdatesOut(
        repo_hash=repo.repo_hash,
        updates_available=remote_hash != repo.repo_hash,
        remote_hash=remote_hash,
    )


@router.post("/{repo_hash}/sync")
def sync_repository(
    repo_hash: str,
    clerk_id: str = Depends(get_current_user),
) -> StreamingResponse:
    """Sync a repo to its latest remote commit, streaming progress via SSE.

    Re-ingests (or reuses an already-indexed newer commit), re-points the
    caller's conversations for this repo to the new commit, and tombstones old
    commits that no conversation references (retaining cited chunks). The heavy
    work runs in a background thread; `progress` events stream until a final
    `result` (or `error`) event.
    """
    db = SessionLocal()
    repo = _require_repo_by_hash(db, clerk_id, repo_hash)
    try:
        remote_hash = GitHubAPIFetcher().remote_head_sha(repo.repo_url)
    except Exception as exc:
        db.close()
        raise HTTPException(status_code=502, detail=f"Failed to probe remote repository: {exc}")

    if remote_hash == repo.repo_hash:
        result = {"status": "up_to_date", "repo_hash": repo.repo_hash}
        db.close()
        return _sse_response([{"type": "result", "result": result, "done": True}])
    db.close()

    progress_q: Queue = Queue()

    def emit(stage: str, percent: int, message: str) -> None:
        progress_q.put({"type": "progress", "stage": stage, "progress": percent, "message": message})

    def _run() -> None:
        db2 = SessionLocal()
        try:
            target = indexed_repo_by_hash(db2, remote_hash)
            if target is None:
                result_obj = Orchestrator().run(repo.repo_url, on_progress=emit)
                get_or_create_indexed_repo(
                    db2,
                    repo_hash=result_obj.repo_hash,
                    repo_name=result_obj.repo_name,
                    repo_url=result_obj.repo_url,
                    file_count=result_obj.files_discovered,
                    chunks_count=result_obj.chunks_created,
                    status="indexed",
                )
                if result_obj.graph is not None:
                    save_repo_graph(db2, result_obj.repo_hash, result_obj.graph)
                target = indexed_repo_by_hash(db2, result_obj.repo_hash)
                if target is None:
                    raise RuntimeError("Sync finalized row missing")
            else:
                emit("sync", 100, "Latest commit already indexed — updating references")

            target_hash = target.repo_hash
            commits = (
                db2.query(IndexedRepo)
                .filter(
                    IndexedRepo.repo_url == repo.repo_url,
                    IndexedRepo.status != "deleted",
                )
                .all()
            )
            old_hashes = [c.repo_hash for c in commits if c.repo_hash != target_hash]
            if old_hashes:
                db2.query(Conversation).filter(
                    Conversation.clerk_id == clerk_id,
                    Conversation.repo_hash.in_(old_hashes),
                ).update({Conversation.repo_hash: target_hash}, synchronize_session=False)
                db2.commit()

            tombstoned: list[str] = []
            for old in commits:
                if old.repo_hash == target_hash:
                    continue
                still_referenced = (
                    db2.query(Conversation.id)
                    .filter(Conversation.repo_hash == old.repo_hash)
                    .first()
                    is not None
                )
                if still_referenced:
                    continue
                keep = cited_chunk_ids(db2, old.repo_hash)
                try:
                    delete_points_by_repo_hash(old.repo_hash, keep_chunk_ids=keep)
                except Exception:
                    logger.exception("Qdrant cleanup failed for %s", old.repo_hash)
                db2.query(FileSummary).filter(FileSummary.repo_hash == old.repo_hash).delete()
                db2.query(RepoGraph).filter(RepoGraph.repo_hash == old.repo_hash).delete()
                old.status = "deleted"
                tombstoned.append(old.repo_hash)
                db2.commit()

            progress_q.put(
                {
                    "type": "result",
                    "result": {
                        "status": "synced",
                        "repo_hash": target_hash,
                        "files_discovered": target.file_count,
                        "chunks_created": target.chunks_count,
                        "tombstoned": tombstoned,
                    },
                    "done": True,
                }
            )
        except Exception as exc:
            logger.exception("Sync failed for %s", repo.repo_url)
            progress_q.put({"type": "error", "error": str(exc), "done": True})
        finally:
            db2.close()

    threading.Thread(target=_run, daemon=True).start()

    def event_stream():
        while True:
            try:
                event = progress_q.get(timeout=10)
            except Empty:
                yield ": ping\n\n"
                continue
            yield _sse(event)
            if event.get("done"):
                break

    return StreamingResponse(event_stream(), media_type="text/event-stream")
