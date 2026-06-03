"""
Embedding pipeline

Handles:
- Load chunks from data/chunks/{repo_name}.pkl
- Skip already embedded chunks via Qdrant lookup
- Embed and upsert to Qdrant in batches
- Delete pickle after successful upsert
"""

import os
import pickle
from functools import lru_cache
from pathlib import Path
from typing import List

from tqdm import tqdm

from chunking.chunk_model import CodeChunk
from embedding.embedder import Embedder
from vector_store.indexer import VectorIndexer


CHUNKS_DIR = Path("data/chunks")
COLLECTION_NAME = "code_chunks"


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    return Embedder()


class EmbeddingPipeline:

    def __init__(self):
        self.embedder = get_embedder()
        self.indexer = VectorIndexer(
            collection_name=COLLECTION_NAME,
            embedding_dim=self.embedder.embedding_dim
        )

    def embed_repo(self, repo_name: str):

        pickle_path = CHUNKS_DIR / f"{repo_name}.pkl"

        if not pickle_path.exists():
            print(f"[EmbeddingPipeline] No chunks found for: {repo_name}")
            return

        if pickle_path.stat().st_size == 0:
            print(f"[EmbeddingPipeline] Chunk file is empty and cannot be loaded: {pickle_path}")
            return

        try:
            with open(pickle_path, "rb") as f:
                raw_chunks = pickle.load(f)
        except EOFError:
            print(f"[EmbeddingPipeline] Chunk file is corrupted or incomplete: {pickle_path}")
            return
        except pickle.UnpicklingError:
            print(f"[EmbeddingPipeline] Chunk file could not be unpickled: {pickle_path}")
            return

        chunks: List[CodeChunk] = []
        for item in raw_chunks:
            if isinstance(item, CodeChunk):
                chunks.append(item)
            elif isinstance(item, dict):
                chunks.append(CodeChunk(**item))
            else:
                print(f"[EmbeddingPipeline] Skipping unsupported chunk record type: {type(item)!r}")

        if not chunks:
            print(f"[EmbeddingPipeline] No valid chunks were loaded from: {pickle_path}")
            return

        print(f"[EmbeddingPipeline] Loaded {len(chunks)} chunks for {repo_name}")

        # Filter already indexed chunks
        new_chunks = [
            chunk for chunk in tqdm(chunks, desc="Checking Qdrant")
            if not self.indexer.exists(chunk.chunk_id)
        ]

        # new_chunks = chunks  #===============================================================

        print(f"[EmbeddingPipeline] {len(chunks) - len(new_chunks)} already indexed, {len(new_chunks)} to embed")

        if not new_chunks:
            print("[EmbeddingPipeline] Nothing to embed, cleaning up pickle...")
            self._cleanup(pickle_path)
            return

        # Embed
        embeddings = self.embedder.embed_chunks(new_chunks)

        # Index to Qdrant
        self.indexer.index(new_chunks, embeddings)

        # Cleanup pickle
        self._cleanup(pickle_path)

    def _cleanup(self, pickle_path: Path):
        os.remove(pickle_path)
        print(f"[EmbeddingPipeline] Deleted: {pickle_path}")

        if not any(CHUNKS_DIR.iterdir()):
            CHUNKS_DIR.rmdir()
            print(f"[EmbeddingPipeline] Removed empty dir: {CHUNKS_DIR}")