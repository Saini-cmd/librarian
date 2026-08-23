import json
import logging
import threading
from datetime import datetime
from queue import Queue

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Iterator

from backend.auth import get_current_user
from core.db import SessionLocal, get_db
from backend.ingest_lock import GlobalIngestGate, IngestLock, start_lock_heartbeat
from core.models import Conversation, FileSummary, IndexedRepo, RepoGraph
from backend.sse import sse, sse_response, stream_queue
from backend.reset import COLLECTION_NAME
from core.usage import check_usage, record_usage
from core.repositories.conversations import cited_chunk_ids
from core.repositories.graph import load_repo_graph, save_repo_graph
from core.repositories.indexed_repo import (
    get_or_create_indexed_repo,
    indexed_repo_by_hash,
    list_user_repos,
    user_repo_exists,
)
from core.repositories.users import upsert_user
from ingestion.github_api_fetcher import GitHubAPIFetcher
from orchestration.orchestrator import Orchestrator
from core.prompts import EXPLAIN_SYSTEM_PROMPT, explain_user_prompt
from rag.llm_client import LLMClient
from rag.types import LLMConfig
from summarization.summary_store import SummaryStore
from symbol_graph.graph_builder import GRAPH_VERSION, build_repo_graph
from vector_store.indexer import (
    chunk_from_payload,
    delete_points_by_repo_hash,
    scroll_chunks_by_file,
)
from vector_store.qdrant_client import QdrantManager


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/repositories", tags=["repositories"])

WAITING_SSE = {
    "type": "progress",
    "stage": "waiting",
    "progress": 5,
    "message": "Latest commit is being indexed by another user — waiting for it to finish…",
}


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


# Per-commit rebuild lock: concurrent requests that hit a missing/stale graph
# build it once; the rest wait and read the persisted result (double-checked).
_REBUILD_LOCKS: dict[str, threading.Lock] = {}
_REBUILD_LOCKS_META = threading.Lock()


def _rebuild_lock_for(repo_hash: str) -> threading.Lock:
    with _REBUILD_LOCKS_META:
        lock = _REBUILD_LOCKS.get(repo_hash)
        if lock is None:
            lock = threading.Lock()
            _REBUILD_LOCKS[repo_hash] = lock
        return lock


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
    if graph is None or graph.get("version", 0) < GRAPH_VERSION:
        with _rebuild_lock_for(repo.repo_hash):
            graph = load_repo_graph(db, repo.repo_hash)
            if graph is None or graph.get("version", 0) < GRAPH_VERSION:
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
    check_usage(user.clerk_id, "explain")
    repo = _require_repo_by_hash(db, user.clerk_id, repo_hash)
    llm_client = LLMClient(config=LLMConfig(max_tokens=350))
    loc = f" lines {payload.start_line}-{payload.end_line}" if payload.start_line else ""
    user_prompt = explain_user_prompt(
        label=payload.label or payload.kind,
        kind=payload.kind,
        file_path=payload.file_path,
        loc=loc,
        code=payload.code,
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
        else:
            # Completed stream = one LLM call spent; record against the message cap.
            record_usage(user.clerk_id, "explain")
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


def _commit_indexed(repo_hash: str) -> bool:
    """True iff a commit's indexed_repo row is usable (status='indexed')."""
    db = SessionLocal()
    try:
        row = indexed_repo_by_hash(db, repo_hash)
        return row is not None and row.status == "indexed"
    finally:
        db.close()


def _sync_run(
    repo: IndexedRepo,
    remote_hash: str,
    clerk_id: str,
    progress_q: Queue,
    lock: IngestLock | None,
    gate: GlobalIngestGate | None = None,
) -> None:
    """Background sync work: ensure the target commit is indexed (only when we
    hold the ingest lock + a global gate slot), re-point the caller's
    conversations, tombstone old commits. Releases the lock/slot when this
    thread owns them."""

    def emit(stage: str, percent: int, message: str) -> None:
        progress_q.put({"type": "progress", "stage": stage, "progress": percent, "message": message})

    def _run() -> None:
        db2 = None
        heartbeat_stop = start_lock_heartbeat(lock, gate) if lock is not None else None
        try:
            # Only a usable row (status='indexed') can be reused — a 'failed' or
            # 'indexing' row is re-ingested when we hold the ingest lock.
            db2 = SessionLocal()
            target = indexed_repo_by_hash(db2, remote_hash)
            usable = target is not None and target.status == "indexed"

            if not usable and lock is not None:
                # We own the ingest lock: run the pipeline WITHOUT holding a
                # DB connection for the whole (minutes-long) run.
                record_usage(clerk_id, "repo_sync")
                db2.close()
                db2 = None
                result_obj = Orchestrator().run(repo.repo_url, on_progress=emit)
                db2 = SessionLocal()
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
            elif not usable:
                raise RuntimeError("Target commit became unavailable before sync finalized")
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
            if db2 is not None:
                db2.close()
            if heartbeat_stop is not None:
                heartbeat_stop.set()
            if lock is not None:
                lock.release()
            if gate is not None:
                gate.release()

    threading.Thread(target=_run, daemon=True).start()


def _sync_event_stream(
    repo: IndexedRepo,
    remote_hash: str,
    clerk_id: str,
) -> Iterator[str]:
    """SSE generator: wait for the target commit to be indexed (or take over its
    ingest), then re-point + tombstone in a background thread and stream."""
    lock = IngestLock()
    gate = GlobalIngestGate.maybe()
    gen = lock.wait_for_index(remote_hash, is_ready=lambda: _commit_indexed(remote_hash), gate=gate)
    try:
        while True:
            state = next(gen)
            if state == "waiting":
                yield sse(WAITING_SSE)
    except StopIteration as exc:
        status = exc.value

    if status == "timeout":
        yield sse(
            {
                "type": "error",
                "error": "Timed out waiting for the latest commit to be indexed. Try again.",
                "done": True,
            }
        )
        return

    progress_q: Queue = Queue()
    if status == "owned":
        _sync_run(repo, remote_hash, clerk_id, progress_q, lock=lock, gate=gate)
    else:
        _sync_run(repo, remote_hash, clerk_id, progress_q, lock=None)
    yield from stream_queue(progress_q)


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

    Wait-and-reuse: the target commit's ingest is serialized by the ingest
    lock. If another user is already ingesting the target, this call streams a
    `waiting` state until the commit is indexed, then re-points + tombstones.
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
        return sse_response([{"type": "result", "result": result, "done": True}])
    db.close()

    # Only the re-ingest path consumes ingest quota: an up-to-date sync no-op
    # above costs nothing, so it is not gated/recorded.
    check_usage(clerk_id, "repo_sync")

    return StreamingResponse(
        _sync_event_stream(repo, remote_hash, clerk_id),
        media_type="text/event-stream",
    )
