from __future__ import annotations

from dataclasses import asdict
import json
import shutil
import os
from functools import lru_cache
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from chunking.chunk_pipeline import ChunkPipeline
from embedding.embedding_pipeline import EmbeddingPipeline
from ingestion.ingestion_pipeline import IngestionPipeline
from retrieval.retrieval_pipeline import RetrievalPipeline
from rag.local.answer_generator import AnswerGenerator

app = FastAPI(title="Librarian AI API", version="0.1.0")
EMBEDDING_PRELOADER = ThreadPoolExecutor(max_workers=1)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProcessRequest(BaseModel):
    repo_url: str = Field(..., min_length=1)
    mode: str = Field(default="local", description="Answer mode: 'local' or 'external'")
    wipe_db: bool = Field(default=False, description="If true, wipe existing DB and chunks before ingest")


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    mode: str | None = Field(default=None, description="Optional override: 'local' or 'external'")


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
    "indexed_repo_name": None,
}

INDEX_STATE_FILE = Path("data/chunks/index_state.json")
REPO_MARKER_FILE = Path("data/chunks/lynko")
QA_RESPONSE_FILE = Path("data/responses/latest.md")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/process", response_model=ProcessResponse)
def process_repository(payload: ProcessRequest) -> ProcessResponse:
    repo_name = _repo_name_from_url(payload.repo_url)

    if not payload.wipe_db and _repo_marker_matches(repo_name):
        APP_STATE.update({
            "phase": "ready",
            "progress": 100,
            "message": f"Repository {repo_name} is already indexed.",
            "ready": True,
            "mode": payload.mode,
            "indexed_repo_name": repo_name,
        })

        return ProcessResponse(
            repo_url=payload.repo_url,
            repo_name=repo_name,
            files_discovered=0,
            chunks_created=0,
            message="Repository already indexed. Reusing existing chunks and embeddings.",
        )

    # Reset previous repository state so the next chat only sees the new repo.
    _reset_index_state(payload.wipe_db)

    embedding_future = prime_embedding_pipeline()

    # Update state: starting
    APP_STATE.update({"phase": "processing", "progress": 5, "message": "Starting ingestion...", "ready": False})

    ingestion = IngestionPipeline()
    files = ingestion.ingest(payload.repo_url)
    APP_STATE.update({"progress": 20, "message": f"Cloned {len(files)} files"})

    chunker = ChunkPipeline()
    chunks = chunker.chunk_repository(files, repo_name=repo_name)
    APP_STATE.update({"progress": 55, "message": f"Created {len(chunks)} chunks"})

    embedder = embedding_future.result()
    APP_STATE.update({"progress": 70, "message": "Embedding chunks..."})
    embedder.embed_repo(repo_name)

    # Remember the selected mode so subsequent /api/chat calls default to it.
    APP_STATE.update({"mode": payload.mode})
    APP_STATE.update({"indexed_repo_name": repo_name})

    # Finalize
    APP_STATE.update({"phase": "ready", "progress": 100, "message": "Repository ingested and indexed.", "ready": True})
    _write_repo_marker(repo_name)
    _write_index_state(repo_name=repo_name, files_discovered=len(files), chunks_created=len(chunks))

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
    # Determine which generator to use: request override -> app state -> default local
    desired_mode = payload.mode or APP_STATE.get("mode") or "local"

    answer_gen = get_answer_generator(mode=desired_mode)
    # Use streaming to let the LLM client return streamed tokens which are
    # reassembled into the full text on the server side before sending to frontend.
    result = answer_gen.generate(query=payload.message, retrieved_chunks=retrieved, stream=True)
    _write_qa_markdown(
        repo_name=str(APP_STATE.get("indexed_repo_name") or "unknown"),
        query=payload.message,
        mode=desired_mode,
        answer=result.answer,
        citations=[asdict(c) for c in result.citations],
    )

    return ChatResponse(answer=result.answer, citations=[asdict(c) for c in result.citations])


@app.post("/api/chat/stream")
def chat_stream(payload: ChatRequest):
    """Stream the LLM answer as Server-Sent Events (SSE) to the frontend.

    For external providers that support streaming, this endpoint relays tokens as
    SSE `data: <token>` events. For local/non-streaming providers it falls back
    to sending the full answer as a single SSE event.
    """
    retriever = get_retrieval_pipeline()
    retrieved = retriever.retrieve(payload.message)
    desired_mode = payload.mode or APP_STATE.get("mode") or "local"

    # Build the prompt the same way the answer generator does.
    if desired_mode == "external":
        from rag.external.answer_generator import AnswerGenerator as ExternalAnswerGenerator

        gen = ExternalAnswerGenerator()
        context = gen.context_builder.build(retrieved)
        prompt_payload = gen.prompt_builder.build(query=payload.message, context=context)
        llm_client = gen.llm_client

        def event_stream():
            full_answer: list[str] = []
            try:
                for token in llm_client.stream_generate(prompt_payload.messages):
                    full_answer.append(token)
                    yield f"data: {json.dumps({'token': token})}\n\n"
            except Exception as exc:
                yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
            else:
                _write_qa_markdown(
                    repo_name=str(APP_STATE.get("indexed_repo_name") or "unknown"),
                    query=payload.message,
                    mode=desired_mode,
                    answer="".join(full_answer),
                    citations=[],
                )
            yield f"data: {json.dumps({'done': True})}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    # Fallback: non-streaming local generator — send full text as single event
    answer_gen = get_answer_generator(mode=desired_mode)
    result = answer_gen.generate(query=payload.message, retrieved_chunks=retrieved, stream=False)
    _write_qa_markdown(
        repo_name=str(APP_STATE.get("indexed_repo_name") or "unknown"),
        query=payload.message,
        mode=desired_mode,
        answer=result.answer,
        citations=[asdict(c) for c in result.citations],
    )

    def single_event():
        yield f"data: {json.dumps({'token': result.answer})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(single_event(), media_type="text/event-stream")


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
def get_embedding_pipeline() -> EmbeddingPipeline:
    """Cache the embedding stack so the model stays loaded after warmup."""
    return EmbeddingPipeline()


def prime_embedding_pipeline():
    """Load the embedding model in the background while ingestion is running."""
    return EMBEDDING_PRELOADER.submit(get_embedding_pipeline)


@lru_cache(maxsize=4)
def get_answer_generator(mode: str = "local") -> AnswerGenerator:
    mode = (mode or "local").strip().lower()
    if mode == "external":
        from rag.external.answer_generator import AnswerGenerator as ExternalAnswerGenerator

        return ExternalAnswerGenerator()

    # Default to local
    return AnswerGenerator()


def _reset_index_state(wipe: bool = True) -> None:
    """Clear old vector/chunk artifacts before ingesting a new repository.

    If `wipe` is False, do not delete the Qdrant collection or existing chunk files.
    """
    from vector_store.qdrant_client import QdrantManager

    if wipe:
        try:
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
            if REPO_MARKER_FILE.exists():
                REPO_MARKER_FILE.unlink()
            if INDEX_STATE_FILE.exists():
                INDEX_STATE_FILE.unlink()
            if QA_RESPONSE_FILE.exists():
                QA_RESPONSE_FILE.unlink()
        except Exception:
            # If wiping fails for any reason, continue without raising to avoid blocking ingestion.
            pass

    APP_STATE.update({"phase": "idle", "progress": 0, "message": "idle", "ready": False})


def _repo_marker_matches(repo_name: str) -> bool:
    """Return True when the marker file already contains the current repo name."""
    if not REPO_MARKER_FILE.exists():
        return False

    try:
        marker_text = REPO_MARKER_FILE.read_text(encoding="utf-8")
    except Exception:
        return False

    if repo_name not in marker_text:
        return False

    return _collection_exists("code_chunks")


def _load_index_state() -> dict[str, Any]:
    if not INDEX_STATE_FILE.exists():
        return {}

    try:
        return json.loads(INDEX_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_index_state(repo_name: str, files_discovered: int, chunks_created: int) -> None:
    try:
        INDEX_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        INDEX_STATE_FILE.write_text(
            json.dumps(
                {
                    "repo_name": repo_name,
                    "files_discovered": files_discovered,
                    "chunks_created": chunks_created,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        # The marker is only used for fast reuse checks; failing to write it should not block ingest.
        pass


def _write_repo_marker(repo_name: str) -> None:
    try:
        REPO_MARKER_FILE.parent.mkdir(parents=True, exist_ok=True)
        REPO_MARKER_FILE.write_text(repo_name, encoding="utf-8")
    except Exception:
        pass


def _write_qa_markdown(repo_name: str, query: str, mode: str, answer: str, citations: list[dict[str, Any]]) -> None:
    try:
        QA_RESPONSE_FILE.parent.mkdir(parents=True, exist_ok=True)
        citation_lines = [
            f"- [{citation.get('citation_id', '')}] {citation.get('file_path', '')}:{citation.get('start_line', '')}-{citation.get('end_line', '')}"
            for citation in citations
            if citation
        ]

        md = [
            f"# QA Response",
            f"- Repo: {repo_name}",
            f"- Mode: {mode}",
            "",
            "## Question",
            query,
            "",
            "## Answer",
            answer,
        ]

        if citation_lines:
            md.extend(["", "## Citations", *citation_lines])

        QA_RESPONSE_FILE.write_text("\n".join(md).rstrip() + "\n", encoding="utf-8")
    except Exception:
        pass
