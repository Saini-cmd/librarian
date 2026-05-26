from dataclasses import dataclass, field
import os
from typing import Any

from chunking.chunk_model import CodeChunk


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: CodeChunk
    score: float
    rrf_score: float | None = None
    vector_score: float | None = None
    bm25_score: float | None = None


@dataclass(frozen=True)
class ContextChunk:
    citation_id: str
    chunk: CodeChunk
    rank_score: float
    token_count: int


@dataclass(frozen=True)
class Citation:
    citation_id: str
    chunk_id: str
    file_path: str
    start_line: int
    end_line: int
    symbol: str
    language: str


@dataclass(frozen=True)
class ContextAssembly:
    chunks: list[ContextChunk]
    grouped_by_file: dict[str, list[ContextChunk]]
    citations: dict[str, Citation]
    total_tokens: int


@dataclass(frozen=True)
class PromptPayload:
    system_prompt: str
    user_prompt: str
    context_text: str
    messages: list[dict[str, str]]


@dataclass(frozen=True)
class LLMConfig:
    model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "gemma4:e2b-it-q4_K_M"))
    base_url: str = field(default_factory=lambda: os.getenv("OLLAMA_HOST", "http://localhost:11434"))
    temperature: float = 0.1
    max_tokens: int = 1024
    timeout_seconds: float = 300.0
    retries: int = 3
    retry_backoff_seconds: float = 1.0


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class AnswerResult:
    query: str
    answer: str
    citations: list[Citation]
    context_chunks: list[ContextChunk]
    llm_model: str
