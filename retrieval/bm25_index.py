import logging
import os
import threading
from collections import OrderedDict
from typing import Any

from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from qdrant_client.models import FieldCondition, Filter, MatchValue

from chunking.chunk_model import CodeChunk
from vector_store.indexer import chunk_from_payload
from vector_store.qdrant_client import QdrantManager


logger = logging.getLogger(__name__)

# Bounded per-process cache: at most this many repo BM25 indexes are kept in
# memory (LRU). Building an index scrolls every chunk of a commit — with many
# repos, an unbounded cache would leak memory under concurrent chat.
BM25_CACHE_SIZE = int(os.getenv("BM25_CACHE_SIZE", "16"))


class BM25Index:
    """
    BM25 keyword index built from Qdrant payloads using LangChain's BM25Retriever.

    Thread-safe: the shared ``RetrievalPipeline`` singleton serves concurrent
    requests, so the per-repo index cache is guarded. Builds run under a
    per-repo lock (different repos build in parallel; the same repo builds
    once, others wait), and cache reads/writes/LRU eviction run under a short
    global lock.
    """

    def __init__(
        self,
        collection_name: str = "code_chunks",
        top_k: int = 20,
        cache_size: int | None = None,
    ):
        self.collection_name = collection_name
        self.top_k = top_k
        self.client = QdrantManager().get_client()

        self._cache_size = cache_size if cache_size is not None else BM25_CACHE_SIZE
        self._retrievers: OrderedDict[str | None, BM25Retriever | None] = OrderedDict()
        self._cache_lock = threading.Lock()
        self._build_locks: dict[str | None, threading.Lock] = {}
        self._build_locks_meta = threading.Lock()

    def _build_lock_for(self, repo_hash: str | None) -> threading.Lock:
        with self._build_locks_meta:
            lock = self._build_locks.get(repo_hash)
            if lock is None:
                lock = threading.Lock()
                self._build_locks[repo_hash] = lock
            return lock

    def _get_retriever(self, repo_hash: str | None) -> BM25Retriever | None:
        with self._cache_lock:
            if repo_hash in self._retrievers:
                self._retrievers.move_to_end(repo_hash)
                return self._retrievers[repo_hash]

        # Not built — build under the per-repo lock so a slow build for one
        # commit never blocks searches on other commits.
        with self._build_lock_for(repo_hash):
            with self._cache_lock:
                if repo_hash in self._retrievers:  # another thread built it meanwhile
                    self._retrievers.move_to_end(repo_hash)
                    return self._retrievers[repo_hash]

            retriever = self._build(repo_hash)

            with self._cache_lock:
                self._retrievers[repo_hash] = retriever
                self._retrievers.move_to_end(repo_hash)
                while len(self._retrievers) > self._cache_size:
                    self._retrievers.popitem(last=False)
            return retriever

    def search(
        self,
        query: str,
        top_k: int | None = None,
        repo_hash: str | None = None,
    ) -> list[dict[str, Any]]:
        retriever = self._get_retriever(repo_hash)
        if retriever is None:
            return []

        limit = top_k or self.top_k
        docs = retriever.invoke(query)[:limit]

        results: list[dict[str, Any]] = []
        for rank, doc in enumerate(docs, start=1):
            chunk = doc.metadata.get("_chunk")
            if chunk is None:
                continue
            results.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "chunk": chunk,
                    "score": float(doc.metadata.get("score", 0.0)),
                    "rank": rank,
                    "source": "bm25",
                }
            )

        logger.info("BM25 retrieval returned %d results", len(results))
        return results

    def _build(self, repo_hash: str | None = None) -> BM25Retriever | None:
        chunks = self._load_chunks_from_qdrant(repo_hash)
        if not chunks:
            logger.warning("BM25 build skipped: no chunks available")
            return None

        documents = []
        for chunk in chunks:
            text = "\n".join([chunk.content, chunk.symbol, chunk.file_path, chunk.language])
            documents.append(Document(page_content=text, metadata={"_chunk": chunk}))

        retriever = BM25Retriever.from_documents(documents)
        retriever.k = self.top_k
        logger.info("BM25 index built with %d chunks", len(chunks))
        return retriever

    def _load_chunks_from_qdrant(
        self, repo_hash: str | None = None
    ) -> list[CodeChunk]:
        chunks: list[CodeChunk] = []
        offset = None
        scroll_filter = None
        if repo_hash:
            scroll_filter = Filter(
                must=[FieldCondition(key="repo_hash", match=MatchValue(value=repo_hash))]
            )

        while True:
            points, next_offset = self.client.scroll(
                collection_name=self.collection_name,
                limit=512,
                offset=offset,
                scroll_filter=scroll_filter,
                with_payload=True,
                with_vectors=False,
            )

            if not points:
                break

            for point in points:
                payload = point.payload or {}
                chunk = chunk_from_payload(payload)
                if chunk is not None:
                    chunks.append(chunk)

            if next_offset is None:
                break
            offset = next_offset

        return chunks
