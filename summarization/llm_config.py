"""Shared summarization LLM config.

Both the ingestion `FileSummarizer` and the chat-memory `rollup_session_summary`
worker summarize with the same cheap model via OpenRouter (OpenAI-compatible
`/api/v1`). One `SUMMARIZE_*` config keeps both consumers consistent and
flip-back-able (set `SUMMARIZE_MODEL`/`SUMMARIZE_BASE_URL`/`SUMMARIZE_API_KEY`).
"""

import os

from dotenv import load_dotenv

from rag.types import LLMConfig


load_dotenv()

_DEFAULT_MODEL = "inclusionai/ling-3.0-flash"
_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


def build_summarizer_config() -> LLMConfig:
    """OpenRouter `ling-3.0-flash` config for cheap, batched summarization.

    Falls back to `OPENROUTER_API_KEY` when `SUMMARIZE_API_KEY` is unset.
    """
    return LLMConfig(
        api_key=os.getenv("SUMMARIZE_API_KEY") or os.getenv("OPENROUTER_API_KEY", ""),
        model=os.getenv("SUMMARIZE_MODEL", _DEFAULT_MODEL),
        base_url=os.getenv("SUMMARIZE_BASE_URL", _DEFAULT_BASE_URL),
        temperature=0.1,
        max_tokens=int(os.getenv("SUMMARIZE_MAX_TOKENS", "300")),
    )
