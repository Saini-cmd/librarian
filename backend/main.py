from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from functools import lru_cache
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import SessionLocal, get_db, init_db
from backend.routers import conversations, repositories, users
from backend.state import (
    add_message,
    collection_exists,
    get_or_create_conversation,
    pipeline_state_dict,
    record_user_repo,
    repo_name_from_url,
    reset_index_state,
    save_qa_record,
    update_pipeline_state,
    upsert_user,
    user_repo_exists,
)
from orchestration.orchestrator import Orchestrator
from rag.answer_generator import AnswerGenerator
from rag.context_builder import ContextBuilder
from rag.llm_client import LLMClient
from rag.prompt_builder import PromptBuilder
from retrieval.retrieval_pipeline import RetrievalPipeline


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Librarian AI API", version="0.2.0", lifespan=lifespan)

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


class ProcessResponse(BaseModel):
    repo_url: str
    repo_name: str
    files_discovered: int
    chunks_created: int
    message: str


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


@app.post("/api/process", response_model=ProcessResponse)
def process_repository(
    payload: ProcessRequest,
    clerk_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProcessResponse:
    repo_name = repo_name_from_url(payload.repo_url)
    user = upsert_user(db, clerk_id)

    if user_repo_exists(db, user.id, repo_name):
        update_pipeline_state(
            db,
            phase="ready",
            progress=100,
            message=f"Repository {repo_name} is already indexed.",
            stage=f"Repository {repo_name} is already indexed.",
            ready=True,
            indexed_repo_name=repo_name,
        )
        return ProcessResponse(
            repo_url=payload.repo_url,
            repo_name=repo_name,
            files_discovered=0,
            chunks_created=0,
            message="Repository already indexed. Reusing existing chunks and embeddings.",
        )

    update_pipeline_state(
        db,
        phase="processing",
        progress=0,
        message="Processing new repository...",
        stage="Starting repository processing",
        ready=False,
    )

    try:
        update_pipeline_state(
            db,
            phase="processing",
            progress=5,
            message="Starting ingestion...",
            stage="Ingesting repository",
        )

        orchestrator = Orchestrator()
        result = orchestrator.run(payload.repo_url)

        update_pipeline_state(
            db,
            phase="ready",
            progress=100,
            message="Repository ingested and indexed.",
            stage="Ready for chat",
            ready=True,
            indexed_repo_name=result.repo_name,
        )

        record_user_repo(
            db,
            user_id=user.id,
            repo_name=result.repo_name,
            repo_url=payload.repo_url,
            files_discovered=result.files_discovered,
            chunks_created=result.chunks_created,
        )

        return ProcessResponse(
            repo_url=payload.repo_url,
            repo_name=result.repo_name,
            files_discovered=result.files_discovered,
            chunks_created=result.chunks_created,
            message="Repository ingested, chunked, summarized, and embedded successfully.",
        )
    except Exception as e:
        update_pipeline_state(
            db,
            phase="error",
            progress=0,
            message=f"Error: {str(e)}",
            stage="Error occurred",
            ready=False,
        )
        raise


@app.post("/api/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    clerk_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    user = upsert_user(db, clerk_id)
    state = pipeline_state_dict(db)
    repo_name = state.get("indexed_repo_name")

    conv_id = _parse_conversation_id(payload.conversation_id)
    conversation = get_or_create_conversation(
        db,
        user_id=user.id,
        conversation_id=conv_id,
        title=payload.message[:60],
        repo_name=repo_name,
    )
    add_message(db, conversation.id, "user", payload.message)

    retriever = get_retrieval_pipeline()
    retrieved = retriever.retrieve(payload.message)

    result = get_answer_generator().generate(
        query=payload.message, retrieved_chunks=retrieved, stream=True
    )
    add_message(db, conversation.id, "assistant", result.answer)
    _persist_qa(db, repo_name, payload.message, result.answer, result.citations)

    return ChatResponse(answer=result.answer, citations=[asdict(c) for c in result.citations])


@app.post("/api/chat/stream")
def chat_stream(payload: ChatRequest, clerk_id: str = Depends(get_current_user)):
    db = SessionLocal()
    user = upsert_user(db, clerk_id)
    state = pipeline_state_dict(db)
    repo_name = state.get("indexed_repo_name")

    conv_id = _parse_conversation_id(payload.conversation_id)
    conversation = get_or_create_conversation(
        db,
        user_id=user.id,
        conversation_id=conv_id,
        title=payload.message[:60],
        repo_name=repo_name,
    )
    add_message(db, conversation.id, "user", payload.message)

    retriever = get_retrieval_pipeline()
    retrieved = retriever.retrieve(payload.message)

    context_builder = ContextBuilder(max_chunks=8, token_budget=14000)
    prompt_builder = PromptBuilder()
    llm_client = LLMClient()

    context = context_builder.build(retrieved)
    prompt_payload = prompt_builder.build(query=payload.message, context=context)

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
            add_message(db, conversation.id, "assistant", answer)
            _persist_qa(db, repo_name, payload.message, answer, [])
        finally:
            db.close()
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/status")
def status(db: Session = Depends(get_db)) -> dict[str, Any]:
    state = pipeline_state_dict(db)
    state.update({
        "qdrant_collection": collection_exists("code_chunks"),
        "stage": state.get("message", "idle"),
    })
    return state


def _parse_conversation_id(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def _persist_qa(db: Session, repo_name: str | None, query: str, answer: str, citations) -> None:
    save_qa_record(
        db,
        repo_name=str(repo_name or "unknown"),
        query=query,
        answer=answer,
        citations=[asdict(c) for c in citations],
    )


@lru_cache(maxsize=1)
def get_retrieval_pipeline() -> RetrievalPipeline:
    return RetrievalPipeline()


@lru_cache(maxsize=1)
def get_answer_generator() -> AnswerGenerator:
    return AnswerGenerator()
