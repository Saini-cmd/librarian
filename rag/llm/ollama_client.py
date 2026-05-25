import json
import logging
import os
import time
from typing import Iterator

import requests
from dotenv import load_dotenv

from rag.types import LLMConfig, LLMResponse


logger = logging.getLogger(__name__)

load_dotenv()


class OllamaClient:
    """Ollama chat client with retries and streaming support."""

    def __init__(
        self,
        config: LLMConfig | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self.config = config or LLMConfig()
        resolved_base_url = base_url or self.config.base_url or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.base_url = resolved_base_url.rstrip("/")
        self.model = model or self.config.model
        self.chat_url = f"{self.base_url}/api/chat"

    def generate(self, messages: list[dict[str, str]], stream: bool = False) -> LLMResponse:
        if stream:
            chunks = []
            for token in self.stream_generate(messages):
                chunks.append(token)
            text = "".join(chunks)
            return LLMResponse(text=text, model=self.model, raw={"streamed": True, "base_url": self.base_url})

        payload = self._payload(messages=messages, stream=False)
        response_json = self._post_with_retries(payload)
        text = self._extract_text(response_json)
        model = str(response_json.get("model", self.model))

        logger.info("stage=llm_response model=%s chars=%d", model, len(text))
        return LLMResponse(text=text, model=model, raw=response_json)

    def stream_generate(self, messages: list[dict[str, str]]) -> Iterator[str]:
        payload = self._payload(messages=messages, stream=True)
        headers = self._headers()
        with requests.post(
            self.chat_url,
            headers=headers,
            json=payload,
            timeout=self.config.timeout_seconds,
            stream=True,
        ) as response:
            if response.status_code >= 400:
                self._log_http_error(response)
                response.raise_for_status()

            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue

                parsed = self._parse_stream_line(line)
                if not parsed:
                    continue

                chunk = self._extract_stream_text(parsed)
                if chunk:
                    yield chunk

                if parsed.get("done"):
                    break

    def _post_with_retries(self, payload: dict) -> dict:
        headers = self._headers()
        last_error: Exception | None = None

        for attempt in range(1, self.config.retries + 1):
            try:
                response = requests.post(
                    self.chat_url,
                    headers=headers,
                    json=payload,
                    timeout=self.config.timeout_seconds,
                )
                if response.status_code >= 400:
                    self._log_http_error(response, attempt=attempt)
                response.raise_for_status()
                return response.json()
            except Exception as exc:  # requests exceptions + decode errors
                last_error = exc
                logger.warning(
                    "stage=llm_retry attempt=%d/%d error=%s",
                    attempt,
                    self.config.retries,
                    str(exc),
                )
                if attempt < self.config.retries:
                    sleep_s = self.config.retry_backoff_seconds * (2 ** (attempt - 1))
                    time.sleep(sleep_s)

        raise RuntimeError(f"Ollama request failed after retries: {last_error}")

    def _payload(self, messages: list[dict[str, str]], stream: bool) -> dict:
        return {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            },
        }

    @staticmethod
    def _headers() -> dict[str, str]:
        return {"Content-Type": "application/json"}

    @staticmethod
    def _parse_stream_line(line: str) -> dict | None:
        text = line.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.debug("stage=ollama_stream_unparsed line=%s", text[:200])
            return None

    @staticmethod
    def _extract_stream_text(response_json: dict) -> str:
        message = response_json.get("message", {})
        if isinstance(message, dict):
            content = message.get("content", "")
            if isinstance(content, str):
                return content

        content = response_json.get("response", "")
        if isinstance(content, str):
            return content

        return str(content)

    def _log_http_error(self, response: requests.Response, attempt: int | None = None) -> None:
        detail = response.text[:1000]
        prefix = f"stage=llm_error_detail attempt={attempt} " if attempt is not None else "stage=llm_error_detail "
        logger.warning("%sstatus=%s detail=%s", prefix, response.status_code, detail)

    @staticmethod
    def _extract_text(response_json: dict) -> str:
        message = response_json.get("message", {})
        if isinstance(message, dict):
            content = message.get("content", "")
            if isinstance(content, str):
                return content

        content = response_json.get("response", "")
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            text_parts = [part.get("text", "") for part in content if isinstance(part, dict)]
            return "".join(text_parts)

        return str(content)