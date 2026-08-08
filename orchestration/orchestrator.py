import logging
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from chunking.chunk_pipeline import ChunkPipeline
from embedding.embedding_pipeline import EmbeddingPipeline
from ingestion.ingestion_pipeline import IngestionPipeline
from summarization.summarization_pipeline import SummarizationPipeline
from symbol_graph.graph_builder import build_repo_graph_from_chunks
from backend.state import ensure_repo_indexing, mark_repo_failed, normalize_repo_url


logger = logging.getLogger(__name__)


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
        files = self.ingestion.ingest(repo_url)
        logger.info("Ingested %d files", len(files))
        progress("scan", 15, f"Discovered {len(files)} files")

        repo_dir = Path("data/repos") / repo_name
        repo_hash = None
        chunks: list = []
        try:
            repo_hash = self.ingestion.fetcher.head_sha(repo_dir)
            logger.info("HEAD commit for %s is %s", repo_name, repo_hash)
            progress("index", 20, f"Commit {repo_hash[:7]}")

            ensure_repo_indexing(repo_hash, repo_name, repo_url)

            for f in files:
                f["repo_hash"] = repo_hash

            # Parallel: summarization (slow per-file LLM) runs in a worker
            # thread while chunking -> embedding proceed in the main thread.
            # Both consume only `files`, so there is no ordering dependency;
            # summarization is idempotent and uses its own DB sessions.
            progress("chunk", 35, "Chunking code...")
            with ThreadPoolExecutor(max_workers=2) as pool:
                summary_future = pool.submit(self.summarizer.summarize, files, repo_hash)

                chunks = self.chunker.chunk_repository(files)
                logger.info("Created %d chunks", len(chunks))
                progress("chunk", 50, f"Created {len(chunks)} chunks")

                progress("summarize_embed", 60, "Summarizing files & embedding chunks...")
                self.embedder.embed_chunks(chunks)
                logger.info("Embedding complete")

                summary_future.result()
            logger.info("Summarization complete")
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
