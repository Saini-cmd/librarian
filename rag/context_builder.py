import logging
import re
from collections import defaultdict

from rag.types import Citation, ContextAssembly, ContextChunk, RetrievedChunk


logger = logging.getLogger(__name__)
_TOKEN_PATTERN = re.compile(r"\S+")


class ContextBuilder:
    """Builds a bounded, deduplicated context from retrieved chunks."""

    def __init__(self, max_chunks: int = 8, token_budget: int = 14000):
        self.max_chunks = max_chunks
        self.token_budget = token_budget

    def build(self, retrieved_chunks: list[RetrievedChunk | dict]) -> ContextAssembly:
        normalized = [self._normalize(item) for item in retrieved_chunks]
        normalized.sort(key=lambda item: item.score, reverse=True)

        selected: list[RetrievedChunk] = []
        seen_chunk_ids: set[str] = set()
        line_spans_by_file: dict[str, list[tuple[int, int]]] = defaultdict(list)
        token_count = 0

        for candidate in normalized:
            chunk = candidate.chunk
            if chunk.chunk_id in seen_chunk_ids:
                continue

            if self._overlaps_existing(chunk.file_path, chunk.start_line, chunk.end_line, line_spans_by_file):
                continue

            chunk_tokens = self._estimate_tokens(chunk.content)
            if token_count + chunk_tokens > self.token_budget:
                continue

            selected.append(candidate)
            seen_chunk_ids.add(chunk.chunk_id)
            line_spans_by_file[chunk.file_path].append((chunk.start_line, chunk.end_line))
            token_count += chunk_tokens

            if len(selected) >= self.max_chunks:
                break

        context_chunks: list[ContextChunk] = []
        grouped_by_file: dict[str, list[ContextChunk]] = defaultdict(list)
        citations: dict[str, Citation] = {}

        for idx, item in enumerate(selected, start=1):
            citation_id = f"C{idx}"
            chunk_tokens = self._estimate_tokens(item.chunk.content)

            context_chunk = ContextChunk(
                citation_id=citation_id,
                chunk=item.chunk,
                rank_score=float(item.score),
                token_count=chunk_tokens,
            )
            context_chunks.append(context_chunk)
            grouped_by_file[item.chunk.file_path].append(context_chunk)
            citations[citation_id] = Citation(
                citation_id=citation_id,
                chunk_id=item.chunk.chunk_id,
                file_path=item.chunk.file_path,
                start_line=item.chunk.start_line,
                end_line=item.chunk.end_line,
                symbol=item.chunk.symbol,
                language=item.chunk.language,
            )

        logger.info(
            "stage=context_builder selected=%d token_budget=%d total_tokens=%d",
            len(context_chunks),
            self.token_budget,
            token_count,
        )

        return ContextAssembly(
            chunks=context_chunks,
            grouped_by_file=dict(grouped_by_file),
            citations=citations,
            total_tokens=token_count,
        )

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        # Lightweight estimator for production-safe pre-filtering.
        return len(_TOKEN_PATTERN.findall(text))

    @staticmethod
    def _overlaps_existing(
        file_path: str,
        start_line: int,
        end_line: int,
        spans_by_file: dict[str, list[tuple[int, int]]],
    ) -> bool:
        for existing_start, existing_end in spans_by_file.get(file_path, []):
            if start_line <= existing_end and end_line >= existing_start:
                return True
        return False

    @staticmethod
    def _normalize(item: RetrievedChunk | dict) -> RetrievedChunk:
        if isinstance(item, RetrievedChunk):
            return item

        return RetrievedChunk(
            chunk=item["chunk"],
            score=float(item.get("score", 0.0)),
            rrf_score=item.get("rrf_score"),
            vector_score=item.get("vector_score"),
            bm25_score=item.get("bm25_score"),
        )
