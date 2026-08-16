"""
Eval ingestion: ingest a repo twice (naive + AST) into isolated eval collections.

Production ``code_chunks`` is never touched. Each eval repo is scoped by its
``repo_hash`` inside two dedicated collections: ``code_chunks_eval_naive``
(fixed-size token chunks for every file) and ``code_chunks_eval_ast`` (the
production AST/text routing). Embedding is incremental — chunks already present
for that commit are skipped, so re-runs are cheap.
"""

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from qdrant_client.models import FieldCondition, Filter, MatchValue

from chunking.chunk_model import CodeChunk
from chunking.chunk_pipeline import ChunkPipeline
from chunking.text_chunker import TextChunker
from embedding.api_embedder import APIEmbedder
from ingestion.ingestion_pipeline import IngestionPipeline
from vector_store.indexer import VectorIndexer
from vector_store.qdrant_client import QdrantManager


logger = logging.getLogger(__name__)

EVAL_NAIVE_COLLECTION = "code_chunks_eval_naive"
EVAL_AST_COLLECTION = "code_chunks_eval_ast"


@dataclass
class EvalIngestResult:
    repo_name: str
    repo_url: str
    repo_hash: str
    naive_chunks: list[CodeChunk]
    ast_chunks: list[CodeChunk]


def chunk_naive(files: list[dict]) -> list[CodeChunk]:
    """Chunk every file with the fixed-size token splitter (no AST routing)."""
    chunker = TextChunker()
    chunks: list[CodeChunk] = []
    for file_metadata in files:
        chunks.extend(chunker.chunk_file(file_metadata))
    return chunks


def ingest_repo_for_eval(
    repo_url: str,
    embed: bool = True,
    embedder: APIEmbedder | None = None,
    progress: Callable[[str, int, int], None] | None = None,
) -> EvalIngestResult:
    """Clone + scan a repo, chunk it twice, and embed both variants.

    The cloned directory is always cleaned up. Returns both chunk lists so the
    runner can build golden sets and run retrieval without extra Qdrant scans.

    ``progress`` (if given) is called as ``progress(collection, done, total)``
    as embedding batches complete, so callers can render a progress bar.
    """
    pipeline = IngestionPipeline()
    repo_name = _repo_name(repo_url)

    logger.info("eval_ingest_start repo=%s", repo_url)
    files, repo_dir = pipeline.ingest(repo_url)
    try:
        repo_hash = pipeline.fetcher.head_sha(repo_dir)
        for file_metadata in files:
            file_metadata["repo_hash"] = repo_hash
        logger.info("eval_ingest hash=%s files=%d", repo_hash[:7], len(files))

        ast_chunks = ChunkPipeline().chunk_repository(files)
        naive_chunks = chunk_naive(files)
        logger.info(
            "eval_chunked ast=%d naive=%d", len(ast_chunks), len(naive_chunks)
        )

        if embed:
            if embedder is None:
                embedder = APIEmbedder()
            embedded_naive = _embed_into(
                EVAL_NAIVE_COLLECTION,
                repo_hash,
                naive_chunks,
                embedder,
                progress=progress,
            )
            embedded_ast = _embed_into(
                EVAL_AST_COLLECTION,
                repo_hash,
                ast_chunks,
                embedder,
                progress=progress,
            )
            logger.info(
                "eval_embedded naive=%d ast=%d (skipped existing)",
                embedded_naive,
                embedded_ast,
            )

        return EvalIngestResult(
            repo_name=repo_name,
            repo_url=repo_url,
            repo_hash=repo_hash,
            naive_chunks=naive_chunks,
            ast_chunks=ast_chunks,
        )
    finally:
        if repo_dir.exists():
            shutil.rmtree(repo_dir)
            logger.info("eval_ingest_cleanup dir=%s", repo_dir)


def _embed_into(
    collection: str,
    repo_hash: str,
    chunks: list[CodeChunk],
    embedder: APIEmbedder,
    progress: Callable[[str, int, int], None] | None = None,
) -> int:
    """Embed a commit's chunks unless that commit is already present.

    Chunk ids are UUIDs (re-generated every run), so existence is checked at the
    commit level: if any point exists for ``repo_hash`` the whole commit is
    considered already ingested and embedding is skipped (re-runs are cheap).
    """
    if _has_repo_chunks(collection, repo_hash):
        return 0

    indexer = VectorIndexer(collection, embedding_dim=embedder.embedding_dim)
    vectors = embedder.embed_chunks(
        chunks,
        progress=(
            (lambda done, total: progress(collection, done, total))
            if progress
            else None
        ),
    )
    indexer.index(chunks, vectors)
    return len(chunks)


def _has_repo_chunks(collection: str, repo_hash: str) -> bool:
    """True iff the collection already holds any chunks for this commit."""
    client = QdrantManager().get_client()
    if not client.collection_exists(collection_name=collection):
        return False
    flt = Filter(
        must=[FieldCondition(key="repo_hash", match=MatchValue(value=repo_hash))]
    )
    result = client.count(
        collection_name=collection,
        count_filter=flt,
        exact=True,
    )
    return result.count > 0


def _repo_name(repo_url: str) -> str:
    parsed = urlparse(repo_url.strip())
    name = Path(parsed.path).name
    return name[:-4] if name.endswith(".git") else name
