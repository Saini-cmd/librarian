from __future__ import annotations

from dataclasses import asdict
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.auth import get_current_user
from backend.state import (
    collection_exists,
    repo_marker_matches,
    repo_name_from_url,
    reset_index_state,
    write_index_state,
    write_qa_markdown,
    write_repo_marker,
)
from orchestration.orchestrator import Orchestrator
from rag.answer_generator import AnswerGenerator
from rag.context_builder import ContextBuilder
from rag.llm_client import LLMClient
from rag.prompt_builder import PromptBuilder
from retrieval.retrieval_pipeline import RetrievalPipeline


app = FastAPI(title="Librarian AI API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProcessRequest(BaseModel):
    repo_url: str = Field(..., min_length=1)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)


class ProcessResponse(BaseModel):
    repo_url: str
    repo_name: str
    files_discovered: int
    chunks_created: int
    message: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[dict[str, Any]] = []


APP_STATE: dict[str, Any] = {
    "phase": "idle",
    "progress": 0,
    "message": "idle",
    "ready": False,
    "indexed_repo_name": None,
}


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/reset")
def reset_database() -> dict[str, str]:
    reset_index_state(wipe=True)
    return {"status": "reset", "message": "All data has been wiped."}


@app.post("/api/process", response_model=ProcessResponse)
def process_repository(payload: ProcessRequest, clerk_id: str = Depends(get_current_user)) -> ProcessResponse:
    repo_name = repo_name_from_url(payload.repo_url)

    if repo_marker_matches(repo_name):
        APP_STATE.update({
            "phase": "ready",
            "progress": 100,
            "message": f"Repository {repo_name} is already indexed.",
            "stage": f"Repository {repo_name} is already indexed.",
            "ready": True,
            "indexed_repo_name": repo_name,
        })
        return ProcessResponse(
            repo_url=payload.repo_url,
            repo_name=repo_name,
            files_discovered=0,
            chunks_created=0,
            message="Repository already indexed. Reusing existing chunks and embeddings.",
        )

    APP_STATE.update({
        "phase": "processing",
        "progress": 0,
        "message": "Processing new repository...",
        "stage": "Starting repository processing",
        "ready": False,
    })

    try:
        APP_STATE.update({
            "phase": "processing",
            "progress": 5,
            "message": "Starting ingestion...",
            "stage": "Ingesting repository",
        })

        orchestrator = Orchestrator()
        result = orchestrator.run(payload.repo_url)

        APP_STATE.update({"indexed_repo_name": result.repo_name})

        APP_STATE.update({
            "phase": "ready",
            "progress": 100,
            "message": "Repository ingested and indexed.",
            "stage": "Ready for chat",
            "ready": True,
        })

        write_repo_marker(result.repo_name)
        write_index_state(
            repo_name=result.repo_name,
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
        APP_STATE.update({
            "phase": "error",
            "progress": 0,
            "message": f"Error: {str(e)}",
            "stage": "Error occurred",
            "ready": False,
        })
        raise


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, clerk_id: str = Depends(get_current_user)) -> ChatResponse:
    retriever = get_retrieval_pipeline()
    retrieved = retriever.retrieve(payload.message)

    result = get_answer_generator().generate(
        query=payload.message, retrieved_chunks=retrieved, stream=True
    )
    write_qa_markdown(
        repo_name=str(APP_STATE.get("indexed_repo_name") or "unknown"),
        query=payload.message,
        answer=result.answer,
        citations=[asdict(c) for c in result.citations],
    )

    return ChatResponse(answer=result.answer, citations=[asdict(c) for c in result.citations])


@app.post("/api/chat/stream")
def chat_stream(payload: ChatRequest, clerk_id: str = Depends(get_current_user)):
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
            write_qa_markdown(
                repo_name=str(APP_STATE.get("indexed_repo_name") or "unknown"),
                query=payload.message,
                answer="".join(full_answer),
                citations=[],
            )
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/status")
def status() -> dict[str, Any]:
    chunks_dir = Path("data/chunks")
    state = APP_STATE.copy()
    state.update({
        "qdrant_collection": collection_exists("code_chunks"),
        "chunks_dir": chunks_dir.exists(),
        "stage": APP_STATE.get("message", "idle"),
        "progress": APP_STATE.get("progress", 0),
        "phase": APP_STATE.get("phase", "idle"),
        "ready": APP_STATE.get("ready", False),
    })
    return state


@lru_cache(maxsize=1)
def get_retrieval_pipeline() -> RetrievalPipeline:
    return RetrievalPipeline()


@lru_cache(maxsize=1)
def get_answer_generator() -> AnswerGenerator:
    return AnswerGenerator()
