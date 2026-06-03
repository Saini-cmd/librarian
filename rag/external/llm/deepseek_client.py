from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Iterator

import requests
from dotenv import load_dotenv

from rag.types import LLMResponse


logger = logging.getLogger(__name__)

load_dotenv()


@dataclass(frozen=True)
class DeepSeekConfig:
    api_key: str = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""))
    model: str = field(default_factory=lambda: os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"))
    base_url: str = field(default_factory=lambda: os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    temperature: float = field(default_factory=lambda: float(os.getenv("DEEPSEEK_TEMPERATURE", "0.2")))
    max_output_tokens: int = field(default_factory=lambda: int(os.getenv("DEEPSEEK_MAX_OUTPUT_TOKENS", "1024")))
    timeout_seconds: float = field(default_factory=lambda: float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "120")))
    retries: int = field(default_factory=lambda: int(os.getenv("DEEPSEEK_RETRIES", "3")))
    retry_backoff_seconds: float = field(default_factory=lambda: float(os.getenv("DEEPSEEK_RETRY_BACKOFF_SECONDS", "1.0")))
    reasoning_effort: str = field(default_factory=lambda: os.getenv("DEEPSEEK_REASONING_EFFORT", ""))


class DeepSeekClient:
    """DeepSeek client using the OpenAI-compatible chat/completions API."""

    def __init__(
        self,
        config: DeepSeekConfig | None = None,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        self.config = config or DeepSeekConfig()
        self.api_key = api_key or self.config.api_key
        self.model = model or self.config.model
        resolved_base_url = base_url or self.config.base_url
        self.base_url = resolved_base_url.rstrip("/")
        self.chat_url = f"{self.base_url}/chat/completions"

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

        logger.info("stage=deepseek_response model=%s chars=%d", model, len(text))
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

                parsed = self._parse_sse_line(line)
                if not parsed:
                    continue

                chunk = self._extract_stream_text(parsed)
                if chunk:
                    yield chunk

                if parsed.get("done"):
                    break

    def generate_summary(self, text: str, instruction: str | None = None) -> LLMResponse:
        system_prompt = instruction or (
            "Summarize the provided code file in about 100 words. "
            "Focus on purpose, main components, and notable behavior."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ]
        return self.generate(messages=messages, stream=False)

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
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "stage=deepseek_retry attempt=%d/%d error=%s",
                    attempt,
                    self.config.retries,
                    str(exc),
                )
                if attempt < self.config.retries:
                    sleep_s = self.config.retry_backoff_seconds * (2 ** (attempt - 1))
                    time.sleep(sleep_s)

        raise RuntimeError(f"DeepSeek request failed after retries: {last_error}")

    def _payload(self, messages: list[dict[str, str]], stream: bool) -> dict:
        payload: dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_output_tokens,
        }

        if self.config.reasoning_effort.strip():
            payload["reasoning_effort"] = self.config.reasoning_effort.strip()

        return payload

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    @staticmethod
    def _parse_sse_line(line: str) -> dict | None:
        text = line.rstrip("\r")
        if not text:
            return None

        if text.startswith("data:"):
            text = text.removeprefix("data:")
            if text.startswith(" "):
                text = text[1:]

        if text == "[DONE]":
            return {"done": True}

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.debug("stage=deepseek_stream_unparsed line=%s", text[:200])
            return None

    @staticmethod
    def _extract_stream_text(response_json: dict) -> str:
        choices = response_json.get("choices", [])
        if not isinstance(choices, list) or not choices:
            return ""

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            return ""

        delta = first_choice.get("delta", {})
        if isinstance(delta, dict):
            content = delta.get("content", "")
            if isinstance(content, str):
                return content

        message = first_choice.get("message", {})
        if isinstance(message, dict):
            content = message.get("content", "")
            if isinstance(content, str):
                return content

        content = first_choice.get("text", "")
        if isinstance(content, str):
            return content

        return ""

    @staticmethod
    def _extract_text(response_json: dict) -> str:
        choices = response_json.get("choices", [])
        if not isinstance(choices, list):
            return ""

        for choice in choices:
            if not isinstance(choice, dict):
                continue

            message = choice.get("message", {})
            if isinstance(message, dict):
                content = message.get("content", "")
                if isinstance(content, str):
                    return content

            delta = choice.get("delta", {})
            if isinstance(delta, dict):
                content = delta.get("content", "")
                if isinstance(content, str):
                    return content

            content = choice.get("text", "")
            if isinstance(content, str):
                return content

        return ""

    def _log_http_error(self, response: requests.Response, attempt: int | None = None) -> None:
        detail = response.text[:1000]
        prefix = f"stage=deepseek_error_detail attempt={attempt} " if attempt is not None else "stage=deepseek_error_detail "
        logger.warning("%sstatus=%s detail=%s", prefix, response.status_code, detail)