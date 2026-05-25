import logging
import re
from collections.abc import Iterable
from typing import Any

from rank_bm25 import BM25Okapi

from chunking.chunk_model import CodeChunk
from vector_store.qdrant_client import QdrantManager


logger = logging.getLogger(__name__)
_TOKEN_PATTERN = re.compile(r"\w+", flags=re.UNICODE)


class BM25Index:
    """
    BM25 keyword index built from chunk content + symbol + file_path + language.

    The index is populated from Qdrant payloads so it can run independently from
    transient local pickle files.
    """

    def __init__(self, collection_name: str = "code_chunks", top_k: int = 20):
        self.collection_name = collection_name
        self.top_k = top_k
        self.client = QdrantManager().get_client()

        self.bm25: BM25Okapi | None = None
        self.chunk_ids: list[str] = []
        self.chunks_by_id: dict[str, CodeChunk] = {}

    def build(self) -> None:
        chunks = self._load_chunks_from_qdrant()
        if not chunks:
            self.bm25 = None
            self.chunk_ids = []
            self.chunks_by_id = {}
            logger.warning("BM25 build skipped: no chunks available")
            return

        tokenized_corpus: list[list[str]] = []
        chunk_ids: list[str] = []
        chunks_by_id: dict[str, CodeChunk] = {}

        for chunk in chunks:
            doc = self._make_document(chunk)
            tokenized_corpus.append(self._tokenize(doc))
            chunk_ids.append(chunk.chunk_id)
            chunks_by_id[chunk.chunk_id] = chunk

        self.bm25 = BM25Okapi(tokenized_corpus)
        self.chunk_ids = chunk_ids
        self.chunks_by_id = chunks_by_id

        logger.info("BM25 index built with %d chunks", len(self.chunk_ids))

    def search(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        if self.bm25 is None:
            self.build()

        if self.bm25 is None:
            return []

        limit = top_k or self.top_k
        query_tokens = self._tokenize(query)
        scores = self.bm25.get_scores(query_tokens)

        ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)[:limit]

        results: list[dict[str, Any]] = []
        for rank, (idx, score) in enumerate(ranked, start=1):
            chunk_id = self.chunk_ids[idx]
            chunk = self.chunks_by_id[chunk_id]
            results.append(
                {
                    "chunk_id": chunk_id,
                    "chunk": chunk,
                    "score": float(score),
                    "rank": rank,
                    "source": "bm25",
                }
            )

        logger.info("BM25 retrieval returned %d results", len(results))
        return results

    def _load_chunks_from_qdrant(self) -> list[CodeChunk]:
        chunks: list[CodeChunk] = []
        offset = None

        while True:
            points, next_offset = self.client.scroll(
                collection_name=self.collection_name,
                limit=512,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )

            if not points:
                break

            for point in points:
                payload = point.payload or {}
                chunk = self._chunk_from_payload(payload)
                if chunk is not None:
                    chunks.append(chunk)

            if next_offset is None:
                break
            offset = next_offset

        return chunks

    @staticmethod
    def _make_document(chunk: CodeChunk) -> str:
        return "\n".join(
            [
                chunk.content,
                chunk.symbol,
                chunk.file_path,
                chunk.language,
            ]
        )

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [token.lower() for token in _TOKEN_PATTERN.findall(text)]

    @staticmethod
    def _chunk_from_payload(payload: dict[str, Any]) -> CodeChunk | None:
        required_keys = [
            "chunk_id",
            "repo",
            "file_path",
            "absolute_path",
            "extension",
            "chunk_source",
            "language",
            "symbol",
            "node_type",
            "start_line",
            "end_line",
            "content",
        ]
        if not all(key in payload for key in required_keys):
            return None

        return CodeChunk(
            chunk_id=str(payload["chunk_id"]),
            repo=str(payload["repo"]),
            file_path=str(payload["file_path"]),
            absolute_path=str(payload["absolute_path"]),
            extension=str(payload["extension"]),
            chunk_source=str(payload["chunk_source"]),
            language=str(payload["language"]),
            symbol=str(payload["symbol"]),
            node_type=str(payload["node_type"]),
            start_line=int(payload["start_line"]),
            end_line=int(payload["end_line"]),
            content=str(payload["content"]),
        )
