import logging
import os
import re
from collections import defaultdict

from rag.types import Citation, ContextAssembly, ContextChunk, RetrievedChunk


logger = logging.getLogger(__name__)
_TOKEN_PATTERN = re.compile(r"\S+")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


class ContextBuilder:
    """Builds a bounded, deduplicated context from retrieved chunks.

    Policy knobs (all optional; ``None`` reads the matching ``RAG_CONTEXT_*``
    env var, so both the backend chat path and the answer generator inherit the
    same configuration):

    - ``max_chunks`` — hard cap on context size (default 8)
    - ``max_per_file`` — cap chunks per file, keeping the highest-scored ones
    - ``min_score`` — absolute score floor (default off)
    - ``min_score_ratio`` — relative floor vs the top score (default off); the
      top-ranked chunk is always kept
    """

    def __init__(
        self,
        max_chunks: int = 8,
        token_budget: int = 14000,
        max_per_file: int | None = None,
        min_score: float | None = None,
        min_score_ratio: float | None = None,
    ):
        self.max_chunks = max_chunks if max_chunks is not None else _env_int("RAG_CONTEXT_MAX_CHUNKS", 8)
        self.token_budget = token_budget
        self.max_per_file = max_per_file if max_per_file is not None else _env_int("RAG_CONTEXT_MAX_PER_FILE", 0)
        self.min_score = min_score if min_score is not None else _env_float("RAG_CONTEXT_MIN_SCORE", 0.0)
        self.min_score_ratio = min_score_ratio if min_score_ratio is not None else _env_float("RAG_CONTEXT_MIN_SCORE_RATIO", 0.0)

    def build(self, retrieved_chunks: list[RetrievedChunk | dict]) -> ContextAssembly:
        normalized = [self._normalize(item) for item in retrieved_chunks]
        normalized.sort(key=lambda item: item.score, reverse=True)
        normalized = self._apply_policy(normalized)

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
                repo=item.chunk.repo_url,
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
        return len(_TOKEN_PATTERN.findall(text))

    def _apply_policy(self, normalized: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not normalized:
            return normalized
        top = normalized[0]

        if self.min_score_ratio and self.min_score_ratio > 0 and top.score > 0:
            floor = max(self.min_score, top.score * self.min_score_ratio)
        else:
            floor = self.min_score

        if floor and floor > 0:
            normalized = [c for c in normalized if c.score >= floor]

        if self.max_per_file and self.max_per_file > 0:
            per_file: dict[str, int] = {}
            kept: list[RetrievedChunk] = []
            for candidate in normalized:
                file_path = candidate.chunk.file_path
                if per_file.get(file_path, 0) >= self.max_per_file:
                    continue
                per_file[file_path] = per_file.get(file_path, 0) + 1
                kept.append(candidate)
            normalized = kept

        if not normalized:
            normalized = [top]

        logger.info(
            "stage=context_policy applied=%s min_score=%s ratio=%s per_file=%s kept=%d",
            self.min_score > 0 or self.min_score_ratio > 0 or self.max_per_file > 0,
            self.min_score,
            self.min_score_ratio,
            self.max_per_file,
            len(normalized),
        )
        return normalized

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
