from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from functools import lru_cache
from queue import Queue
from typing import Any, Iterator

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.auth import get_current_user, get_current_user_optional
from backend.database import SessionLocal, get_db, init_db
from backend.ingest_lock import GlobalIngestGate, IngestLock, start_lock_heartbeat
from backend.routers import conversations, repositories, users
from backend.sse import sse, sse_response, stream_queue
from backend.usage import check_usage, record_usage
from backend.state import (
    add_message,
    collection_exists,
    get_or_create_conversation,
    get_or_create_indexed_repo,
    indexed_repo_by_hash,
    last_indexed_repo_for_user,
    normalize_repo_url,
    reset_index_state,
    resolve_conversation_repo,
    save_repo_graph,
    upsert_user,
    write_citations,
)
from ingestion.github_api_fetcher import GitHubAPIFetcher
from memory.short_term import build_memory_context
from memory.worker import enqueue_memory_jobs
from orchestration.orchestrator import Orchestrator
from rag.answer_generator import AnswerGenerator
from rag.context_builder import ContextBuilder
from rag.llm_client import LLMClient
from rag.prompt_builder import PromptBuilder
from retrieval.retrieval_pipeline import RetrievalPipeline
from vector_store.qdrant_client import QdrantManager


logger = logging.getLogger(__name__)


WAITING_SSE = {
    "type": "progress",
    "stage": "waiting",
    "progress": 5,
    "message": "Another user is indexing this repository — waiting for it to finish…",
}


# FastAPI runs sync `def` endpoints in a thread pool; the pool size is the
# per-worker chat concurrency ceiling. Env-tunable (default 40, FastAPI's default).
THREADPOOL_SIZE = int(os.getenv("THREADPOOL_SIZE", "40"))

# Comma-separated allowed origins (dev defaults are the Vite dev servers).
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174",
    ).split(",")
    if origin.strip()
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        import anyio

        limiter = anyio.to_thread.current_default_thread_limiter()
        limiter.total_tokens = THREADPOOL_SIZE
    except Exception:
        logger.warning("Could not set threadpool size to %d", THREADPOOL_SIZE, exc_info=True)
    init_db()
    yield


app = FastAPI(title="Librarian AI API", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(conversations.router)
app.include_router(repositories.router)


class ProcessRequest(BaseModel):
    repo_url: str = Field(..., min_length=1)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    conversation_id: str | None = None
    repo_hash: str | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[dict[str, Any]] = []


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _redis_ready() -> bool:
    import redis

    client = redis.Redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    try:
        return bool(client.ping())
    finally:
        client.close()


@app.get("/api/ready")
def readiness() -> JSONResponse:
    """Readiness probe for orchestrators/load balancers.

    200 only when Postgres, Qdrant, and Redis are all reachable; otherwise 503
    with a per-dependency check map. `/api/health` remains the no-dependency
    liveness probe.
    """
    checks: dict[str, bool] = {}

    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        checks["postgres"] = True
    except Exception:
        checks["postgres"] = False
    finally:
        db.close()

    try:
        QdrantManager().get_client().get_collections()
        checks["qdrant"] = True
    except Exception:
        checks["qdrant"] = False

    try:
        checks["redis"] = _redis_ready()
    except Exception:
        checks["redis"] = False

    ready = all(checks.values())
    return JSONResponse(
        {"status": "ok" if ready else "degraded", "checks": checks},
        status_code=200 if ready else 503,
    )


@app.post("/api/reset")
def reset_database(
    clerk_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    reset_index_state(db, wipe=True)
    return {"status": "reset", "message": "All data has been wiped."}


def _repo_ready(db: Session, repo_hash: str) -> object | None:
    """The indexed_repo row if it is genuinely usable (status='indexed')."""
    repo = indexed_repo_by_hash(db, repo_hash)
    return repo if repo is not None and repo.status == "indexed" else None


def _repo_indexed(repo_hash: str) -> bool:
    """True iff a commit's indexed_repo row is usable — short-lived session."""
    db = SessionLocal()
    try:
        return _repo_ready(db, repo_hash) is not None
    finally:
        db.close()


def _reuse_result_events(repo_hash: str, clerk_id: str) -> list[dict]:
    """Open a conversation on an already-indexed commit and build the result event."""
    db = SessionLocal()
    try:
        repo = _repo_ready(db, repo_hash)
        if repo is None:
            return [{"type": "error", "error": "Repository is not available.", "done": True}]
        conv = get_or_create_conversation(
            db,
            clerk_id,
            repo_name=repo.repo_name,
            repo_hash=repo.repo_hash,
        )
        return [
            {
                "type": "result",
                "result": {
                    "repo_url": repo.repo_url,
                    "repo_name": repo.repo_name,
                    "repo_hash": repo.repo_hash,
                    "files_discovered": repo.file_count,
                    "chunks_created": repo.chunks_count,
                    "message": "Repository already indexed at this commit.",
                    "conversation_id": str(conv.id),
                },
                "done": True,
            }
        ]
    finally:
        db.close()


def _run_pipeline(
    repo_url: str,
    clerk_id: str,
    lock: IngestLock,
    progress_q: Queue,
    gate: GlobalIngestGate | None = None,
) -> None:
    """Run the ingest pipeline in a background thread, releasing the ingest
    lock (and the global gate slot, if held) on exit."""

    def emit(stage: str, percent: int, message: str) -> None:
        progress_q.put({"type": "progress", "stage": stage, "progress": percent, "message": message})

    def _run() -> None:
        db2 = None
        heartbeat_stop = start_lock_heartbeat(lock, gate)
        try:
            record_usage(clerk_id, "repo_ingest")
            result_obj = Orchestrator().run(repo_url, on_progress=emit)
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
            conv = get_or_create_conversation(
                db2,
                clerk_id,
                repo_name=result_obj.repo_name,
                repo_hash=result_obj.repo_hash,
            )
            progress_q.put(
                {
                    "type": "result",
                    "result": {
                        "repo_url": result_obj.repo_url,
                        "repo_name": result_obj.repo_name,
                        "repo_hash": result_obj.repo_hash,
                        "files_discovered": result_obj.files_discovered,
                        "chunks_created": result_obj.chunks_created,
                        "message": "Repository ingested, chunked, summarized, and embedded successfully.",
                        "conversation_id": str(conv.id),
                    },
                    "done": True,
                }
            )
        except Exception as exc:
            logger.exception("Pipeline failed for %s", repo_url)
            progress_q.put({"type": "error", "error": str(exc), "done": True})
        finally:
            if db2 is not None:
                db2.close()
            heartbeat_stop.set()
            lock.release()
            if gate is not None:
                gate.release()

    threading.Thread(target=_run, daemon=True).start()


def _process_event_stream(
    repo_url: str,
    clerk_id: str,
    remote_hash: str,
) -> Iterator[str]:
    """SSE generator: acquire the ingest lock (or wait-and-reuse), then stream.

    The lock is acquired lazily here (not in the endpoint body) so the request
    thread never blocks — the holder runs the pipeline in a background thread
    while the SSE stream drains its queue; a concurrent second caller streams
    waiting ticks until the commit is indexed or it takes over.
    """
    lock = IngestLock()
    gate = GlobalIngestGate.maybe()
    gen = lock.wait_for_index(remote_hash, is_ready=lambda: _repo_indexed(remote_hash), gate=gate)
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
                "error": "Timed out waiting for another user's ingest to finish. Try again.",
                "done": True,
            }
        )
        return
    if status == "ready":
        for event in _reuse_result_events(remote_hash, clerk_id):
            yield sse(event)
        return
    # "owned": run the pipeline ourselves. The background thread owns the lock
    # and gate slot until it finishes (released in its finally), so a client
    # disconnect does not free them mid-pipeline.
    progress_q: Queue = Queue()
    _run_pipeline(repo_url, clerk_id, lock, progress_q, gate=gate)
    yield from stream_queue(progress_q)


@app.post("/api/process")
def process_repository(
    payload: ProcessRequest,
    clerk_id: str = Depends(get_current_user),
) -> StreamingResponse:
    """Ingest a repo, streaming progress via SSE.

    Probe-first + wait-and-reuse: if the remote HEAD is already indexed
    (globally, status='indexed') the pipeline is skipped and a conversation is
    opened on that commit. Otherwise the caller takes the ingest lock for that
    commit: the holder runs the pipeline in a background thread (SSE `progress`
    events until a final `result`/`error`); a second concurrent caller for the
    same commit streams a `waiting` state until the commit is indexed (reuse) or
    takes over if the holder gave up.
    """
    db = SessionLocal()
    repo_url = normalize_repo_url(payload.repo_url)
    user = upsert_user(db, clerk_id)

    try:
        remote_hash = GitHubAPIFetcher().remote_head_sha(repo_url)
    except Exception as exc:
        db.close()
        raise HTTPException(
            status_code=502,
            detail=f"Failed to probe remote repository. Check the URL and GITHUB_TOKEN: {exc}",
        )

    existing = _repo_ready(db, remote_hash)
    if existing is not None:
        conv = get_or_create_conversation(
            db,
            user.clerk_id,
            repo_name=existing.repo_name,
            repo_hash=existing.repo_hash,
        )
        result = {
            "repo_url": existing.repo_url,
            "repo_name": existing.repo_name,
            "repo_hash": existing.repo_hash,
            "files_discovered": existing.file_count,
            "chunks_created": existing.chunks_count,
            "message": "Repository already indexed at this commit.",
            "conversation_id": str(conv.id),
        }
        db.close()
        return sse_response([{"type": "result", "result": result, "done": True}])
    db.close()

    # Only the pipeline-runs path consumes ingest quota: skip-to-chat reuse of
    # an already-indexed commit above costs nothing, so it is not gated/recorded.
    check_usage(user.clerk_id, "repo_ingest")

    return StreamingResponse(
        _process_event_stream(repo_url, user.clerk_id, remote_hash),
        media_type="text/event-stream",
    )


@app.post("/api/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    clerk_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    user = upsert_user(db, clerk_id)
    check_usage(user.clerk_id, "chat_message")

    conv_id = _parse_conversation_id(payload.conversation_id)
    repo_hash, repo_name, repo_url = resolve_conversation_repo(
        db, user.clerk_id, conv_id, payload.repo_hash
    )
    conversation = get_or_create_conversation(
        db,
        user.clerk_id,
        conversation_id=conv_id,
        repo_name=repo_name,
        repo_hash=repo_hash,
    )
    history, memory_texts = build_memory_context(
        db, conversation.id, user.clerk_id, repo_url, payload.message
    )
    user_msg = add_message(db, conversation.id, "user", payload.message, repo_hash=repo_hash)

    retriever = get_retrieval_pipeline()
    retrieved = retriever.retrieve(payload.message, repo_hash=repo_hash)

    result = get_answer_generator().generate(
        query=payload.message,
        retrieved_chunks=retrieved,
        stream=True,
        repo_hash=repo_hash,
        history=history.messages,
        memory_texts=memory_texts,
    )
    msg = add_message(
        db,
        conversation.id,
        "assistant",
        result.answer,
        citation=[asdict(c) for c in result.citations],
        repo_hash=repo_hash,
    )
    write_citations(db, msg.id, [asdict(c) for c in result.citations])
    enqueue_memory_jobs(
        conversation.id, user_msg.id, msg.id, user.clerk_id, repo_url, repo_hash
    )
    record_usage(user.clerk_id, "chat_message")

    return ChatResponse(answer=result.answer, citations=[asdict(c) for c in result.citations])


@app.post("/api/chat/stream")
def chat_stream(payload: ChatRequest, clerk_id: str = Depends(get_current_user)):
    db = SessionLocal()
    user = upsert_user(db, clerk_id)
    check_usage(user.clerk_id, "chat_message")

    conv_id = _parse_conversation_id(payload.conversation_id)
    repo_hash, repo_name, repo_url = resolve_conversation_repo(
        db, user.clerk_id, conv_id, payload.repo_hash
    )
    conversation = get_or_create_conversation(
        db,
        user.clerk_id,
        conversation_id=conv_id,
        repo_name=repo_name,
        repo_hash=repo_hash,
    )
    history, memory_texts = build_memory_context(
        db, conversation.id, user.clerk_id, repo_url, payload.message
    )
    user_msg = add_message(db, conversation.id, "user", payload.message, repo_hash=repo_hash)

    retriever = get_retrieval_pipeline()
    retrieved = retriever.retrieve(payload.message, repo_hash=repo_hash)

    context_builder = ContextBuilder()
    prompt_builder = PromptBuilder()
    llm_client = LLMClient()

    context = context_builder.build(retrieved)
    prompt_payload = prompt_builder.build(
        query=payload.message,
        context=context,
        repo_hash=repo_hash,
        history=history.messages,
        memory_texts=memory_texts,
    )

    def event_stream():
        full_answer: list[str] = []
        try:
            for token in llm_client.stream_generate(prompt_payload.messages):
                full_answer.append(token)
                yield f"data: {json.dumps({'token': token})}\n\n"
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
        else:
            answer = "".join(full_answer)
            citations = AnswerGenerator._map_citations(answer, context, repo_hash)
            msg = add_message(
                db,
                conversation.id,
                "assistant",
                answer,
                citation=[asdict(c) for c in citations],
                repo_hash=repo_hash,
            )
            write_citations(db, msg.id, [asdict(c) for c in citations])
            enqueue_memory_jobs(
                conversation.id, user_msg.id, msg.id, user.clerk_id, repo_url, repo_hash
            )
            record_usage(user.clerk_id, "chat_message")
            yield f"data: {json.dumps({'citations': [asdict(c) for c in citations]})}\n\n"
        finally:
            db.close()
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/status")
def status(
    clerk_id: str | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    repo_name = None
    if clerk_id:
        user = upsert_user(db, clerk_id)
        repo_name = last_indexed_repo_for_user(db, user.clerk_id)

    ready = repo_name is not None
    return {
        "phase": "ready" if ready else "idle",
        "progress": 100 if ready else 0,
        "message": f"Latest indexed repository: {repo_name}" if repo_name else "No repositories indexed yet.",
        "stage": repo_name or "idle",
        "ready": ready,
        "indexed_repo_name": repo_name,
        "qdrant_collection": collection_exists("code_chunks"),
    }


def _parse_conversation_id(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


@lru_cache(maxsize=1)
def get_retrieval_pipeline() -> RetrievalPipeline:
    return RetrievalPipeline()


@lru_cache(maxsize=1)
def get_answer_generator() -> AnswerGenerator:
    return AnswerGenerator()
