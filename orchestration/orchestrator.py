import logging
import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from chunking.chunk_pipeline import ChunkPipeline
from embedding.embedding_pipeline import EmbeddingPipeline
from ingestion.ingestion_pipeline import IngestionPipeline
from summarization.summarization_pipeline import SummarizationPipeline
from symbol_graph.graph_builder import build_repo_graph_from_chunks
from core.repositories.indexed_repo import ensure_repo_indexing, mark_repo_failed
from core.url import normalize_repo_url


logger = logging.getLogger(__name__)


# Repo-size gates, enforced BEFORE any LLM/embed API spend so a rejected repo
# costs nothing: file count after the scan (also bounds summarize calls) and
# chunk count after local chunking (bounds embed calls + Qdrant storage).
# 0 disables a gate. Part of the usage-cap system (see DECISIONS.md D37).
USAGE_MAX_REPO_FILES = int(os.getenv("USAGE_MAX_REPO_FILES", "300"))
USAGE_MAX_REPO_CHUNKS = int(os.getenv("USAGE_MAX_REPO_CHUNKS", "6000"))


class RepoSizeError(Exception):
    """Raised when a repo exceeds the configured size gate (files or chunks)."""


@dataclass
class RunResult:
    repo_name: str
    repo_url: str
    repo_hash: str
    files_discovered: int
    chunks_created: int
    graph: dict | None = None


class Orchestrator:
    """Runs the full ingestion pipeline: clone → chunk → summarize → embed → cleanup."""

    def __init__(self):
        self.ingestion = IngestionPipeline()
        self.chunker = ChunkPipeline()
        self.summarizer = SummarizationPipeline()
        self.embedder = EmbeddingPipeline()

    def run(
        self,
        repo_url: str,
        on_progress: Callable[[str, int, str], None] | None = None,
    ) -> RunResult:
        repo_url = normalize_repo_url(repo_url)
        repo_name = self._repo_name(repo_url)

        def progress(stage: str, percent: int, message: str) -> None:
            if on_progress is not None:
                on_progress(stage, percent, message)

        logger.info("Starting pipeline for %s", repo_url)

        progress("ingest", 5, "Cloning & scanning repository...")
        files, repo_dir = self.ingestion.ingest(repo_url)
        logger.info("Ingested %d files", len(files))
        progress("scan", 15, f"Discovered {len(files)} files")

        repo_hash = None
        chunks: list = []
        try:
            if USAGE_MAX_REPO_FILES > 0 and len(files) > USAGE_MAX_REPO_FILES:
                raise RepoSizeError(
                    f"Repository has {len(files)} code files, exceeding the limit of "
                    f"{USAGE_MAX_REPO_FILES}. Pick a smaller repository."
                )

            repo_hash = self.ingestion.fetcher.head_sha(repo_dir)
            logger.info("HEAD commit for %s is %s", repo_name, repo_hash)
            progress("index", 20, f"Commit {repo_hash[:7]}")

            ensure_repo_indexing(repo_hash, repo_name, repo_url)

            for f in files:
                f["repo_hash"] = repo_hash

            # Chunking is local CPU (no API spend) and completes before any
            # LLM/embed call so the chunk-count gate can reject an oversized
            # repo before a single token is spent.
            progress("chunk", 35, "Chunking code...")
            chunks = self.chunker.chunk_repository(files)
            logger.info("Created %d chunks", len(chunks))
            if USAGE_MAX_REPO_CHUNKS > 0 and len(chunks) > USAGE_MAX_REPO_CHUNKS:
                raise RepoSizeError(
                    f"Repository produced {len(chunks)} chunks, exceeding the limit of "
                    f"{USAGE_MAX_REPO_CHUNKS}. Pick a smaller repository."
                )
            progress("chunk", 50, f"Created {len(chunks)} chunks")

            # Parallel: per-file summarization (LLM) and per-chunk embedding
            # (OpenRouter) are independent (consume only `files`/`chunks`) and
            # run concurrently; both are joined and the first failure raises.
            # Each uses its own internal worker pool + DB sessions, so running
            # them side-by-side is thread-safe.
            progress("summarize_embed", 60, "Summarizing files & embedding chunks...")
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [
                    pool.submit(self.summarizer.summarize, files, repo_hash),
                    pool.submit(self.embedder.embed_chunks, chunks),
                ]
                errors: list[BaseException] = []
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as exc:  # noqa: BLE001 — collect & raise first
                        errors.append(exc)
                if errors:
                    raise errors[0]
            logger.info("Summarization & embedding complete")
            progress("embed", 85, "Embedding complete")

            try:
                graph = build_repo_graph_from_chunks(repo_name, chunks)
                logger.info("Symbol graph built (%d nodes, %d edges)", len(graph["nodes"]), len(graph["edges"]))
            except Exception:
                logger.exception("Symbol graph build failed for %s; continuing without it", repo_name)
                graph = None
            progress("graph", 95, "Building symbol graph")
        except Exception:
            if repo_hash:
                mark_repo_failed(repo_hash)
            raise
        finally:
            if repo_dir.exists():
                shutil.rmtree(repo_dir)
                logger.info("Cleaned up %s", repo_dir)

        progress("done", 100, "Complete")
        return RunResult(
            repo_name=repo_name,
            repo_url=repo_url,
            repo_hash=repo_hash,
            files_discovered=len(files),
            chunks_created=len(chunks),
            graph=graph,
        )

    @staticmethod
    def _repo_name(repo_url: str) -> str:
        parsed = urlparse(repo_url.strip())
        name = Path(parsed.path).name
        return name[:-4] if name.endswith(".git") else name
