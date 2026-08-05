import logging
import os
from typing import List

import requests
import tiktoken
from dotenv import load_dotenv

from chunking.chunk_model import CodeChunk


load_dotenv()


logger = logging.getLogger(__name__)

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/embeddings"
_MAX_INPUT_TOKENS = 480
_ENCODING = "cl100k_base"


class APIEmbedder:
    """Unified embedder using OpenRouter API (BAAI/bge-base-en-v1.5).

    Handles both chunk embedding (for indexing) and query embedding (for retrieval).
    """

    def __init__(self, model: str = "BAAI/bge-base-en-v1.5"):
        self.model = model
        self.api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.embedding_dim = 768
        self._tokenizer = tiktoken.get_encoding(_ENCODING)

    def _truncate(self, text: str, max_tokens: int = _MAX_INPUT_TOKENS) -> str:
        tokens = self._tokenizer.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return self._tokenizer.decode(tokens[:max_tokens])

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
