import logging
import os
from typing import Iterator

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from rag.types import LLMConfig, LLMResponse


logger = logging.getLogger(__name__)

load_dotenv()


class LLMClient:
    """Unified LLM client using ChatOpenAI (OpenAI-compatible API, works with DeepSeek)."""

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig()
        self._client = ChatOpenAI(
            model=self.config.model,
            api_key=self.config.api_key or os.getenv("DEEPSEEK_API_KEY"),
            base_url=self.config.base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            timeout=self.config.timeout_seconds,
            max_retries=self.config.retries,
        )

    def generate(self, messages: list[dict[str, str]], stream: bool = False) -> LLMResponse:
        lc_messages = self._to_langchain(messages)

        if stream:
            chunks: list[str] = []
            for chunk in self._client.stream(lc_messages):
                if chunk.content:
                    chunks.append(chunk.content)
            text = "".join(chunks)
        else:
            response = self._client.invoke(lc_messages)
            text = response.content or ""

        return LLMResponse(text=text, model=self.config.model, raw={})

    def stream_generate(self, messages: list[dict[str, str]]) -> Iterator[str]:
        lc_messages = self._to_langchain(messages)
        for chunk in self._client.stream(lc_messages):
            if chunk.content:
                yield chunk.content

    @staticmethod
    def _to_langchain(messages: list[dict[str, str]]) -> list:
        result = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                result.append(SystemMessage(content=content))
            else:
                result.append(HumanMessage(content=content))
        return result
