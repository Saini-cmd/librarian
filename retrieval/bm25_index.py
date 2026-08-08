import logging
from typing import Any

from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from qdrant_client.models import FieldCondition, Filter, MatchValue

from chunking.chunk_model import CodeChunk
from vector_store.indexer import chunk_from_payload
from vector_store.qdrant_client import QdrantManager


logger = logging.getLogger(__name__)


class BM25Index:
    """
    BM25 keyword index built from Qdrant payloads using LangChain's BM25Retriever.
    """

    def __init__(self, collection_name: str = "code_chunks", top_k: int = 20):
        self.collection_name = collection_name
        self.top_k = top_k
        self.client = QdrantManager().get_client()

        self._retrievers: dict[str | None, BM25Retriever | None] = {}

    def search(
        self,
        query: str,
        top_k: int | None = None,
        repo_hash: str | None = None,
    ) -> list[dict[str, Any]]:
        if repo_hash not in self._retrievers:
            self._retrievers[repo_hash] = self._build(repo_hash)

        retriever = self._retrievers[repo_hash]
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
