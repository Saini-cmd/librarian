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
class GeminiConfig:
    api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-3-flash-preview"))
    base_url: str = field(default_factory=lambda: os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"))
    temperature: float = field(default_factory=lambda: float(os.getenv("GEMINI_TEMPERATURE", "0.2")))
    max_output_tokens: int = field(default_factory=lambda: int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "1024")))
    timeout_seconds: float = field(default_factory=lambda: float(os.getenv("GEMINI_TIMEOUT_SECONDS", "120")))
    retries: int = field(default_factory=lambda: int(os.getenv("GEMINI_RETRIES", "3")))
    retry_backoff_seconds: float = field(default_factory=lambda: float(os.getenv("GEMINI_RETRY_BACKOFF_SECONDS", "1.0")))
    store: bool = field(default_factory=lambda: os.getenv("GEMINI_STORE", "false").strip().lower() in {"1", "true", "yes", "on"})


class GeminiClient:
    """Gemini client using the REST generateContent / streamGenerateContent APIs.

    The interface mirrors the local Ollama client so the external pipeline can be
    wired in later for file summaries and QA without changing caller code.
    """

    def __init__(
        self,
        config: GeminiConfig | None = None,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        self.config = config or GeminiConfig()
        self.api_key = api_key or self.config.api_key
        self.model = model or self.config.model
        resolved_base_url = base_url or self.config.base_url
        self.base_url = resolved_base_url.rstrip("/")
        self.generate_url = f"{self.base_url}/models/{self.model}:generateContent"
        self.stream_url = f"{self.base_url}/models/{self.model}:streamGenerateContent"

    def generate(self, messages: list[dict[str, str]], stream: bool = False) -> LLMResponse:
        if stream:
            chunks = []
            for token in self.stream_generate(messages):
                chunks.append(token)
            text = "".join(chunks)
            return LLMResponse(text=text, model=self.model, raw={"streamed": True, "base_url": self.base_url})

        payload = self._build_payload(messages=messages)
        response_json = self._post_with_retries(self.generate_url, payload)
        text = self._extract_text(response_json)
        model = str(response_json.get("modelVersion", self.model))

        logger.info("stage=gemini_response model=%s chars=%d", model, len(text))
        return LLMResponse(text=text, model=model, raw=response_json)

    def stream_generate(self, messages: list[dict[str, str]]) -> Iterator[str]:
        payload = self._build_payload(messages=messages)
        headers = self._headers()
        params = {"key": self.api_key} if self.api_key else None

        with requests.post(
            self.stream_url,
            headers=headers,
            params=params,
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

                chunk = self._parse_sse_line(line)
                if chunk:
                    yield chunk

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

    def _post_with_retries(self, url: str, payload: dict) -> dict:
        headers = self._headers()
        params = {"key": self.api_key} if self.api_key else None
        last_error: Exception | None = None

        for attempt in range(1, self.config.retries + 1):
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    params=params,
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
                    "stage=gemini_retry attempt=%d/%d error=%s",
                    attempt,
                    self.config.retries,
                    str(exc),
                )
                if attempt < self.config.retries:
                    sleep_s = self.config.retry_backoff_seconds * (2 ** (attempt - 1))
                    time.sleep(sleep_s)

        raise RuntimeError(f"Gemini request failed after retries: {last_error}")

    def _build_payload(self, messages: list[dict[str, str]]) -> dict:
        system_instruction: str | None = None
        contents: list[dict[str, object]] = []

        for message in messages:
            role = (message.get("role") or "user").strip().lower()
            content = (message.get("content") or "").strip()
            if not content:
                continue

            if role == "system":
                system_instruction = f"{system_instruction}\n{content}".strip() if system_instruction else content
                continue

            mapped_role = "model" if role in {"assistant", "model"} else "user"
            contents.append(
                {
                    "role": mapped_role,
                    "parts": [{"text": content}],
                }
            )

        payload: dict[str, object] = {
            "contents": contents,
            "store": self.config.store,
            "generationConfig": {
                "temperature": self.config.temperature,
                "maxOutputTokens": self.config.max_output_tokens,
            },
        }

        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        return payload

    @staticmethod
    def _headers() -> dict[str, str]:
        return {"Content-Type": "application/json"}

    @staticmethod
    def _extract_text(response_json: dict) -> str:
        candidates = response_json.get("candidates", [])
        if not isinstance(candidates, list):
            return ""

        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            content = candidate.get("content", {})
            if not isinstance(content, dict):
                continue
            parts = content.get("parts", [])
            if not isinstance(parts, list):
                continue

            text_parts = []
            for part in parts:
                if isinstance(part, dict):
                    text = part.get("text", "")
                    if isinstance(text, str):
                        text_parts.append(text)
            if text_parts:
                return "".join(text_parts)

        return ""

    @staticmethod
    def _parse_sse_line(line: str) -> str | None:
        text = line.strip()
        if not text:
            return None

        if text.startswith("data:"):
            text = text.removeprefix("data:").strip()

        if text == "[DONE]":
            return None

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            logger.debug("stage=gemini_stream_unparsed line=%s", text[:200])
            return None

        return GeminiClient._extract_text(payload) or None

    def _log_http_error(self, response: requests.Response, attempt: int | None = None) -> None:
        detail = response.text[:1000]
        prefix = f"stage=gemini_error_detail attempt={attempt} " if attempt is not None else "stage=gemini_error_detail "
        logger.warning("%sstatus=%s detail=%s", prefix, response.status_code, detail)
