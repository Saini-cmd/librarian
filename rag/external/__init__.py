"""External LLM pipeline namespace (Gemini and other hosted providers)."""

from rag.external.llm import GeminiClient, GeminiConfig

__all__ = ["GeminiClient", "GeminiConfig"]
