from __future__ import annotations

import json
import logging
import threading
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from functools import lru_cache
from queue import Empty, Queue
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth import get_current_user, get_current_user_optional
from backend.database import SessionLocal, get_db, init_db
from backend.routers import conversations, repositories, users
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
from orchestration.orchestrator import Orchestrator
from rag.answer_generator import AnswerGenerator
from rag.context_builder import ContextBuilder
from rag.llm_client import LLMClient
from rag.prompt_builder import PromptBuilder
from retrieval.retrieval_pipeline import RetrievalPipeline


logger = logging.getLogger(__name__)


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _sse_response(events: list[dict]) -> StreamingResponse:
    def gen():
        for event in events:
            yield _sse(event)

    return StreamingResponse(gen(), media_type="text/event-stream")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Librarian AI API", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174"],
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


@app.post("/api/reset")
def reset_database(db: Session = Depends(get_db)) -> dict[str, str]:
    reset_index_state(db, wipe=True)
    return {"status": "reset", "message": "All data has been wiped."}


@app.post("/api/process")
def process_repository(
    payload: ProcessRequest,
    clerk_id: str = Depends(get_current_user),
) -> StreamingResponse:
    """Ingest a repo, streaming progress via SSE.

    Probe-first: if the remote HEAD is already indexed (globally), skip the
    pipeline and open a conversation on that commit. Otherwise the pipeline runs
    in a background thread and emits `progress` events until a final `result`
    (or `error`) event.
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

    existing = indexed_repo_by_hash(db, remote_hash)
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
        return _sse_response([{"type": "result", "result": result, "done": True}])
    db.close()

    progress_q: Queue = Queue()

    def emit(stage: str, percent: int, message: str) -> None:
        progress_q.put({"type": "progress", "stage": stage, "progress": percent, "message": message})

    def _run() -> None:
        db2 = SessionLocal()
        try:
            result_obj = Orchestrator().run(repo_url, on_progress=emit)
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
                user.clerk_id,
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


@app.post("/api/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    clerk_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    user = upsert_user(db, clerk_id)

    conv_id = _parse_conversation_id(payload.conversation_id)
    repo_hash, repo_name = resolve_conversation_repo(
        db, user.clerk_id, conv_id, payload.repo_hash
    )
    conversation = get_or_create_conversation(
        db,
        user.clerk_id,
        conversation_id=conv_id,
        repo_name=repo_name,
        repo_hash=repo_hash,
    )
    add_message(db, conversation.id, "user", payload.message, repo_hash=repo_hash)

    retriever = get_retrieval_pipeline()
    retrieved = retriever.retrieve(payload.message, repo_hash=repo_hash)

    result = get_answer_generator().generate(
        query=payload.message, retrieved_chunks=retrieved, stream=True, repo_hash=repo_hash
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

    return ChatResponse(answer=result.answer, citations=[asdict(c) for c in result.citations])


@app.post("/api/chat/stream")
def chat_stream(payload: ChatRequest, clerk_id: str = Depends(get_current_user)):
    db = SessionLocal()
    user = upsert_user(db, clerk_id)

    conv_id = _parse_conversation_id(payload.conversation_id)
    repo_hash, repo_name = resolve_conversation_repo(
        db, user.clerk_id, conv_id, payload.repo_hash
    )
    conversation = get_or_create_conversation(
        db,
        user.clerk_id,
        conversation_id=conv_id,
        repo_name=repo_name,
        repo_hash=repo_hash,
    )
    add_message(db, conversation.id, "user", payload.message, repo_hash=repo_hash)

    retriever = get_retrieval_pipeline()
    retrieved = retriever.retrieve(payload.message, repo_hash=repo_hash)

    context_builder = ContextBuilder(max_chunks=8, token_budget=14000)
    prompt_builder = PromptBuilder()
    llm_client = LLMClient()

    context = context_builder.build(retrieved)
    prompt_payload = prompt_builder.build(query=payload.message, context=context, repo_hash=repo_hash)

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
