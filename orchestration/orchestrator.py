import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from chunking.chunk_pipeline import ChunkPipeline
from embedding.embedding_pipeline import EmbeddingPipeline
from ingestion.ingestion_pipeline import IngestionPipeline
from summarization.summarization_pipeline import SummarizationPipeline
from symbol_graph.graph_builder import build_repo_graph_from_chunks


logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    repo_name: str
    repo_url: str
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

    def run(self, repo_url: str) -> RunResult:
        repo_name = self._repo_name(repo_url)

        logger.info("Starting pipeline for %s", repo_url)

        files = self.ingestion.ingest(repo_url)
        logger.info("Ingested %d files", len(files))

        chunks = self.chunker.chunk_repository(files)
        logger.info("Created %d chunks", len(chunks))

        self.summarizer.summarize(files, repo_name)
        logger.info("Summarization complete")

        self.embedder.embed_chunks(chunks)
        logger.info("Embedding complete")

        try:
            graph = build_repo_graph_from_chunks(repo_name, chunks)
            logger.info("Symbol graph built (%d nodes, %d edges)", len(graph["nodes"]), len(graph["edges"]))
        except Exception:
            logger.exception("Symbol graph build failed for %s; continuing without it", repo_name)
            graph = None

        repo_dir = Path("data/repos") / repo_name
        if repo_dir.exists():
            shutil.rmtree(repo_dir)
            logger.info("Cleaned up %s", repo_dir)

        return RunResult(
            repo_name=repo_name,
            repo_url=repo_url,
            files_discovered=len(files),
            chunks_created=len(chunks),
            graph=graph,
        )

    @staticmethod
    def _repo_name(repo_url: str) -> str:
        parsed = urlparse(repo_url.strip())
        name = Path(parsed.path).name
        return name[:-4] if name.endswith(".git") else name
