import logging
import os

import requests
from dotenv import load_dotenv

from rag.types import HybridCandidate


load_dotenv()


logger = logging.getLogger(__name__)

OPENROUTER_RERANK_URL = "https://openrouter.ai/api/v1/rerank"


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

        response = requests.post(
            OPENROUTER_RERANK_URL,
            headers=headers,
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()

        return data.get("results", [])
