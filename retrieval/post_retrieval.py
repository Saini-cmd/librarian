from dataclasses import replace

from retrieval.hybrid_retriever import HybridCandidate


PENALTY_DIRS = (
    "test/",
    "tests/",
    "__tests__/",
    "spec/",
    "specs/",
    "fixtures/",
    "examples/",
    "example/",
    "demo/",
    "demos/",
    "docs/",
    "doc/",
    "documentation/",
    "bench/",
    "benchmark/",
    "benchmarks/",
    "scripts/",
    "tools/",
    "tooling/",
    "build/",
    "dist/",
    "out/",
    "coverage/",
    "mock/",
    "mocks/",
    "stubs/",
    "generated/",
    "gen/",
    "tmp/",
    "temp/",
    "vendor/",
    "third_party/",
    "node_modules/",
)

BOOST_DIRS = (
    "src/",
    "lib/",
    "core/",
    "router/",
    "routes/",
    "middleware/",
    "handler/",
    "handlers/",
    "controller/",
    "controllers/",
    "service/",
    "services/",
    "engine/",
    "runtime/",
    "internal/",
    "pkg/",
    "cmd/",
    "modules/",
    "components/",
    "features/",
    "domain/",
    "business/",
    "impl/",
    "implementation/",
    "server/",
    "backend/",
    "api/",
)

class PostRetrievalProcessor:
    """Applies score shaping and deduplication for retrieval candidates/results."""

    def __init__(
        self,
        penalty_weight: float = 0.75,
        boost_weight: float = 1.15,
        ast_boost_weight: float = 1.10,
    ):
        self.penalty_weight = penalty_weight
        self.boost_weight = boost_weight
        self.ast_boost_weight = ast_boost_weight

    def adjust_scores(self, candidates: list[HybridCandidate]) -> list[HybridCandidate]:
        adjusted_candidates: list[HybridCandidate] = []
        for candidate in candidates:
            multiplier = self._file_priority_multiplier(candidate.chunk.file_path)

            if candidate.chunk.chunk_source == "ast":
                multiplier *= self.ast_boost_weight

            adjusted_score = candidate.rrf_score * multiplier
            adjusted_candidates.append(replace(candidate, adjusted_score=adjusted_score))

        adjusted_candidates.sort(
            key=lambda item: item.adjusted_score if item.adjusted_score is not None else item.rrf_score,
            reverse=True,
        )
        return adjusted_candidates

    def dedupe_candidates(self, candidates: list[HybridCandidate]) -> list[HybridCandidate]:
        seen: set[str] = set()
        deduped: list[HybridCandidate] = []

        for candidate in candidates:
            key = self._dedupe_key(
                chunk_id=candidate.chunk.chunk_id,
                file_path=candidate.chunk.file_path,
                start_line=candidate.chunk.start_line,
                end_line=candidate.chunk.end_line,
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(candidate)

        return deduped

    def dedupe_reranked(self, reranked: list[dict], top_k: int = 5) -> list[dict]:
        seen: set[str] = set()
        final: list[dict] = []

        for item in reranked:
            chunk = item["chunk"]
            key = self._dedupe_key(
                chunk_id=chunk.chunk_id,
                file_path=chunk.file_path,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
            )
            if key in seen:
                continue

            seen.add(key)
            final.append(item)
            if len(final) >= top_k:
                break

        return final

    def _file_priority_multiplier(self, file_path: str) -> float:
        path = file_path.lower().replace("\\", "/")
        weight = 1.0

        if any(token in path for token in PENALTY_DIRS):
            weight *= self.penalty_weight

        if any(token in path for token in BOOST_DIRS):
            weight *= self.boost_weight

        return weight

    @staticmethod
    def _dedupe_key(chunk_id: str, file_path: str, start_line: int, end_line: int) -> str:
        if chunk_id:
            return f"id:{chunk_id}"
        return f"loc:{file_path}:{start_line}:{end_line}"
