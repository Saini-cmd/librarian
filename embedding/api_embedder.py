import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Callable, List

import requests
import tiktoken
from dotenv import load_dotenv

from chunking.chunk_model import CodeChunk


load_dotenv()


logger = logging.getLogger(__name__)

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/embeddings"

# BGE models use a BERT/WordPiece tokenizer, NOT cl100k — so a cl100k token
# estimate can undershoot the model's real token count. Truncate with the
# model's own tokenizer (exact) and fall back to a conservative tiktoken cap.
_BGE_MODEL = "BAAI/bge-base-en-v1.5"
_MODEL_MAX_TOKENS = 512
_SAFE_MAX_TOKENS = 505  # leave headroom for special tokens the API may add
_FALLBACK_MAX_TOKENS = 400  # tiktoken estimate with margin for tokenizer mismatch
_ENCODING = "cl100k_base"

# OpenRouter's embeddings endpoint rejects input arrays larger than 1024 items
# ("array_above_max_length"). Batch well under that cap with comfortable token
# headroom per request (~256 x 505 tokens).
EMBED_BATCH_SIZE = 256
EMBED_MAX_WORKERS = 5
EMBED_MAX_RETRIES = 3
EMBED_RETRY_BASE_DELAY = 1.0
_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


@lru_cache(maxsize=1)
def _get_model_tokenizer():
    try:
        from transformers import AutoTokenizer

        return AutoTokenizer.from_pretrained(_BGE_MODEL, use_fast=True)
    except Exception:
        logger.warning(
            "Could not load %s tokenizer; falling back to tiktoken token estimate",
            _BGE_MODEL,
        )
        return None


class APIEmbedder:
    """Unified embedder using OpenRouter API (BAAI/bge-base-en-v1.5).

    Handles both chunk embedding (for indexing) and query embedding (for retrieval).
    """

    def __init__(self, model: str = _BGE_MODEL):
        self.model = model
        self.api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.embedding_dim = 768
        self._tokenizer = tiktoken.get_encoding(_ENCODING)

    def _truncate(self, text: str) -> str:
        tokenizer = _get_model_tokenizer()
        if tokenizer is not None:
            tokens = tokenizer.encode(text, add_special_tokens=False)
            if len(tokens) <= _SAFE_MAX_TOKENS:
                return text
            return tokenizer.decode(tokens[:_SAFE_MAX_TOKENS], skip_special_tokens=True)

        tokens = self._tokenizer.encode(text)
        if len(tokens) <= _FALLBACK_MAX_TOKENS:
            return text
        return self._tokenizer.decode(tokens[:_FALLBACK_MAX_TOKENS])

    def embed_texts(
        self,
        texts: List[str],
        progress: Callable[[int, int], None] | None = None,
    ) -> List[List[float]]:
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not set in environment")

        truncated = [self._truncate(t) for t in texts]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        batches = [
            truncated[i : i + EMBED_BATCH_SIZE]
            for i in range(0, len(truncated), EMBED_BATCH_SIZE)
        ]
        if not batches:
            if progress:
                progress(0, 0)
            return []

        # Fan out per-batch API calls (each batch is independent) across up to
        # EMBED_MAX_WORKERS threads, matching summarization's concurrency.
        # Results are collected by batch index so chunk<->vector order is kept.
        with ThreadPoolExecutor(max_workers=EMBED_MAX_WORKERS) as executor:
            future_map = {
                executor.submit(self._embed_batch, batch, headers): i
                for i, batch in enumerate(batches)
            }
            ordered: List[List[List[float]]] = [None] * len(batches)
            for future, i in future_map.items():
                ordered[i] = future.result()
                if progress:
                    progress(i + 1, len(batches))

        return [vector for batch in ordered for vector in batch]

    def _embed_batch(self, batch: List[str], headers: dict) -> List[List[float]]:
        payload = {
            "model": self.model,
            "input": batch,
        }

        for attempt in range(EMBED_MAX_RETRIES):
            response = requests.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=120,
            )

            if response.status_code == 200:
                data = response.json()
                if "data" not in data:
                    raise RuntimeError(
                        f"OpenRouter embedding API unexpected response: {response.text[:500]}"
                    )
                items = sorted(data["data"], key=lambda x: x["index"])
                return [item["embedding"] for item in items]

            if response.status_code in _RETRYABLE_STATUSES and attempt < EMBED_MAX_RETRIES - 1:
                delay = EMBED_RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "OpenRouter embedding retry %d/%d after status=%d in %ss",
                    attempt + 1,
                    EMBED_MAX_RETRIES,
                    response.status_code,
                    delay,
                )
                time.sleep(delay)
                continue

            raise RuntimeError(
                f"OpenRouter embedding API error (status={response.status_code}): {response.text[:500]}"
            )

    def embed_chunks(
        self,
        chunks: List[CodeChunk],
        progress: Callable[[int, int], None] | None = None,
    ) -> List[List[float]]:
        texts = [self._prepare_text(chunk) for chunk in chunks]
        return self.embed_texts(texts, progress=progress)

    def embed_query(self, query: str) -> List[float]:
        results = self.embed_texts([query])
        return results[0]

    @staticmethod
    def _prepare_text(chunk: CodeChunk) -> str:
        return (
            f"Repository: {chunk.repo_url}\n"
            f"File: {chunk.file_path}\n"
            f"Language: {chunk.language}\n"
            f"Symbol: {chunk.symbol}\n"
            f"Node Type: {chunk.node_type}\n"
            f"Chunk Source: {chunk.chunk_source}\n"
            f"Lines: {chunk.start_line}-{chunk.end_line}\n\n"
            f"{chunk.content}"
        )

