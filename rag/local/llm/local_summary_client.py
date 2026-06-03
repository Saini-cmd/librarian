from __future__ import annotations

import logging
from typing import Optional

from rag.local.llm.ollama_client import OllamaClient
from rag.types import LLMResponse


logger = logging.getLogger(__name__)


class LocalSummaryClient:
    """Simple adapter that exposes `generate_summary(text, instruction)` using OllamaClient."""

    def __init__(self, ollama_client: Optional[OllamaClient] = None):
        self.ollama = ollama_client or OllamaClient()
        # expose api_key attr for compatibility checks
        self.api_key = True

    def generate_summary(self, text: str, instruction: str | None = None) -> LLMResponse:
        system_prompt = instruction or (
            "Summarize the provided code file in about 100 words. "
            "Focus on purpose, main components, and notable behavior."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ]
        return self.ollama.generate(messages=messages, stream=False)
