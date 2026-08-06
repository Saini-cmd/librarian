import logging
import os
from functools import lru_cache
from typing import List

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

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not set in environment")

        truncated = [self._truncate(t) for t in texts]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "input": truncated,
        }

        response = requests.post(
            OPENROUTER_API_URL,
            headers=headers,
            json=payload,
            timeout=120,
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"OpenRouter embedding API error (status={response.status_code}): {response.text[:500]}"
            )

        data = response.json()

        if "data" not in data:
            raise RuntimeError(
                f"OpenRouter embedding API unexpected response: {response.text[:500]}"
            )

        items = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in items]

    def embed_chunks(self, chunks: List[CodeChunk]) -> List[List[float]]:
        texts = [self._prepare_text(chunk) for chunk in chunks]
        return self.embed_texts(texts)

    def embed_query(self, query: str) -> List[float]:
        results = self.embed_texts([query])
        return results[0]

    @staticmethod
    def _prepare_text(chunk: CodeChunk) -> str:
        return (
            f"Repository: {chunk.repo}\n"
            f"File: {chunk.file_path}\n"
            f"Language: {chunk.language}\n"
            f"Symbol: {chunk.symbol}\n"
            f"Node Type: {chunk.node_type}\n"
            f"Chunk Source: {chunk.chunk_source}\n"
            f"Lines: {chunk.start_line}-{chunk.end_line}\n\n"
            f"{chunk.content}"
        )

