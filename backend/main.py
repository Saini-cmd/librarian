from __future__ import annotations

from dataclasses import asdict
import shutil
import os
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from chunking.chunk_pipeline import ChunkPipeline
from embedding.embedding_pipeline import EmbeddingPipeline
from ingestion.ingestion_pipeline import IngestionPipeline
from retrieval.retrieval_pipeline import RetrievalPipeline
from rag.answer_generator import AnswerGenerator

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


# Simple in-memory app state to report progress to frontend.
APP_STATE: dict[str, Any] = {
    "phase": "idle",
    "progress": 0,
    "message": "idle",
    "ready": False,
}


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/process", response_model=ProcessResponse)
def process_repository(payload: ProcessRequest) -> ProcessResponse:
    repo_name = _repo_name_from_url(payload.repo_url)
    # Reset previous repository state so the next chat only sees the new repo.
    _reset_index_state()

    # Update state: starting
    APP_STATE.update({"phase": "processing", "progress": 5, "message": "Starting ingestion...", "ready": False})

    ingestion = IngestionPipeline()
    files = ingestion.ingest(payload.repo_url)
    APP_STATE.update({"progress": 20, "message": f"Cloned {len(files)} files"})

    chunker = ChunkPipeline()
    chunks = chunker.chunk_repository(files, repo_name=repo_name)
    APP_STATE.update({"progress": 55, "message": f"Created {len(chunks)} chunks"})

    embedder = EmbeddingPipeline()
    APP_STATE.update({"progress": 70, "message": "Embedding chunks..."})
    embedder.embed_repo(repo_name)

    # Finalize
    APP_STATE.update({"phase": "ready", "progress": 100, "message": "Repository ingested and indexed.", "ready": True})

    return ProcessResponse(
        repo_url=payload.repo_url,
        repo_name=repo_name,
        files_discovered=len(files),
        chunks_created=len(chunks),
        message="Repository ingested, chunked, and embedded successfully.",
    )


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    # Run retrieval + answer generation synchronously for now.
    retriever = get_retrieval_pipeline()
    retrieved = retriever.retrieve(payload.message)

    answer_gen = get_answer_generator()
    result = answer_gen.generate(query=payload.message, retrieved_chunks=retrieved, stream=False)

    return ChatResponse(answer=result.answer, citations=[asdict(c) for c in result.citations])


@app.get("/api/status")
def status() -> dict[str, Any]:
    chunks_dir = Path("data/chunks")
    state = APP_STATE.copy()
    state.update({
        "qdrant_collection": _collection_exists("code_chunks"),
        "chunks_dir": chunks_dir.exists(),
    })
    return state


def _repo_name_from_url(repo_url: str) -> str:
    parsed = urlparse(repo_url.strip())
    name = Path(parsed.path).name
    if name.endswith(".git"):
        name = name[:-4]
    return name or "repo"


def _collection_exists(collection_name: str) -> bool:
    from vector_store.qdrant_client import QdrantManager

    client = QdrantManager().get_client()
    collections = client.get_collections().collections
    return any(collection.name == collection_name for collection in collections)


@lru_cache(maxsize=1)
def get_retrieval_pipeline() -> RetrievalPipeline:
    """Cache the retrieval stack so it does not reload large models on every chat request."""
    query_device = os.getenv("RAG_QUERY_DEVICE", "cpu")
    reranker_device = os.getenv("RAG_RERANKER_DEVICE", "cpu")
    return RetrievalPipeline(query_device=query_device, reranker_device=reranker_device)


@lru_cache(maxsize=1)
def get_answer_generator() -> AnswerGenerator:
    return AnswerGenerator()


def _reset_index_state() -> None:
    """Clear old vector/chunk artifacts before ingesting a new repository."""
    from vector_store.qdrant_client import QdrantManager

    client = QdrantManager().get_client()

    try:
        if _collection_exists("code_chunks"):
          client.delete_collection("code_chunks")
    except Exception:
        # If the local store is already busy or the collection is missing, continue.
        pass

    chunks_dir = Path("data/chunks")
    if chunks_dir.exists():
        shutil.rmtree(chunks_dir, ignore_errors=True)

    APP_STATE.update({"phase": "idle", "progress": 0, "message": "idle", "ready": False})
