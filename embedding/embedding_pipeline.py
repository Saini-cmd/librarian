"""
Embedding pipeline

Handles:
- Accept chunks directly from chunk_pipeline
- Skip already embedded chunks via Qdrant lookup
- Embed via OpenRouter API
- Upsert to Qdrant
"""

from functools import lru_cache
from typing import List

from tqdm import tqdm

from chunking.chunk_model import CodeChunk
from embedding.api_embedder import APIEmbedder
from vector_store.indexer import VectorIndexer


COLLECTION_NAME = "code_chunks"


@lru_cache(maxsize=1)
def get_embedder() -> APIEmbedder:
    return APIEmbedder()


class EmbeddingPipeline:

    def __init__(self):
        self.embedder = get_embedder()
        self.indexer = VectorIndexer(
            collection_name=COLLECTION_NAME,
            embedding_dim=self.embedder.embedding_dim
        )

    def embed_chunks(self, chunks: List[CodeChunk]) -> None:
        if not chunks:
            print("[EmbeddingPipeline] No chunks to embed")
            return

        print(f"[EmbeddingPipeline] {len(chunks)} chunks to process")

        new_chunks = [
            chunk for chunk in tqdm(chunks, desc="Checking Qdrant")
            if not self.indexer.exists(chunk.chunk_id)
        ]

        print(f"[EmbeddingPipeline] {len(chunks) - len(new_chunks)} already indexed, {len(new_chunks)} to embed")

        if not new_chunks:
            print("[EmbeddingPipeline] Nothing to embed")
            return

        embeddings = self.embedder.embed_chunks(new_chunks)
        self.indexer.index(new_chunks, embeddings)
        print(f"[EmbeddingPipeline] Indexed {len(new_chunks)} chunks")
