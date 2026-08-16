import logging
import os
import time

import requests
from dotenv import load_dotenv

from rag.types import HybridCandidate


load_dotenv()


logger = logging.getLogger(__name__)

OPENROUTER_RERANK_URL = "https://openrouter.ai/api/v1/rerank"

_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0


class OpenRouterReranker:
    """Reranks hybrid retrieval candidates via OpenRouter API (cohere/rerank-4-fast)."""

    def __init__(self, model: str = "cohere/rerank-4-fast"):
        self.model = model
        self.api_key = os.getenv("OPENROUTER_API_KEY", "")

    def rerank(
        self,
        query: str,
        candidates: list[HybridCandidate],
        top_k: int = 10,
    ) -> list[dict]:
        if not candidates:
            return []

        documents = [c.chunk.content for c in candidates]

        results = self._call_api(query, documents, top_k)

        scored: list[dict] = []
        for item in results:
            idx = item["index"]
            candidate = candidates[idx]
            scored.append(
                {
                    "chunk": candidate.chunk,
                    "score": float(item["relevance_score"]),
                    "rrf_score": float(candidate.rrf_score),
                    "vector_score": candidate.vector_score,
                    "bm25_score": candidate.bm25_score,
                }
            )

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def _call_api(self, query: str, documents: list[str], top_n: int) -> list[dict]:
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not set in environment")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "query": query,
            "documents": documents,
            "top_n": top_n,
        }

        for attempt in range(_MAX_RETRIES):
            response = requests.post(
                OPENROUTER_RERANK_URL,
                headers=headers,
                json=payload,
                timeout=60,
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("results", [])

            if (
                response.status_code in _RETRYABLE_STATUSES
                and attempt < _MAX_RETRIES - 1
            ):
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "rerank retry %d/%d after status=%d in %ss",
                    attempt + 1,
                    _MAX_RETRIES,
                    response.status_code,
                    delay,
                )
                time.sleep(delay)
                continue

            response.raise_for_status()

        return []
