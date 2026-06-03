"""
Chunking pipeline

Routes files to:
- AST chunker
- Text chunker
"""

import os
import pickle
import traceback
from functools import lru_cache
import logging
import time
from pathlib import Path
from dataclasses import asdict
from typing import List, Dict

from chunking.ast_chunker import ASTChunker
from chunking.chunk_model import CodeChunk
from chunking.text_chunker import TextChunker
from rag.external.llm.gemini_client import GeminiClient
from rag.local.llm.local_summary_client import LocalSummaryClient
from tqdm import tqdm


SUMMARY_MAX_CHARS = int(os.getenv("GEMINI_SUMMARY_MAX_CHARS", "12000"))


@lru_cache(maxsize=1)
def _get_summary_client() -> GeminiClient:
    provider = os.getenv("SUMMARY_PROVIDER", "external").strip().lower()
    if provider == "local":
        return LocalSummaryClient()
    return GeminiClient()


class ChunkPipeline:

    def __init__(self):
        self.ast_chunker = ASTChunker()
        self.text_chunker = TextChunker()
        self.summary_client = _get_summary_client()
        self._log = logging.getLogger(__name__)

    def chunk_repository(self, files_metadata: List[Dict], repo_name: str) -> List[CodeChunk]:

        all_chunks: List[CodeChunk] = []

        for i, file_metadata in enumerate(tqdm(files_metadata, desc="Chunking files")):

            processing_type = file_metadata.get("processing_type", "text")
            file_path = file_metadata.get("file_path", "unknown")
            file_summary = self._summarize_file(file_metadata)

            try:
                if processing_type == "ast":
                    chunks = self.ast_chunker.chunk_file(file_metadata)
                    all_chunks.extend(chunks)

                elif processing_type == "text":
                    chunks = self.text_chunker.chunk_file(file_metadata)
                    all_chunks.extend(chunks)

                for chunk in chunks:
                    chunk.summary = file_summary

            except Exception:
                traceback.print_exc()
                continue

        self._save_chunks(repo_name, all_chunks)

        return all_chunks

    def _save_chunks(self, repo_name: str, chunks: List[CodeChunk]):

        try:
            chunks_dir = Path("data/chunks")
            chunks_dir.mkdir(parents=True, exist_ok=True)

            output_path = chunks_dir / f"{repo_name}.pkl"
            temp_path = output_path.with_suffix(".pkl.tmp")

            serializable_chunks = [asdict(chunk) for chunk in chunks]

            with open(temp_path, "wb") as f:
                pickle.dump(serializable_chunks, f)

            temp_path.replace(output_path)

            print(f"\nSaved {len(chunks)} chunks → {output_path}")

        except Exception:
            print("Failed to save chunks")
            traceback.print_exc()

    def _summarize_file(self, file_metadata: Dict) -> str:
        if not getattr(self.summary_client, "api_key", ""):
            return ""

        file_path = file_metadata.get("absolute_path")
        if not file_path:
            return ""

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
                content = handle.read()
        except Exception:
            return ""

        if not content.strip():
            return ""

        content = content[:SUMMARY_MAX_CHARS]
        language = file_metadata.get("language", "unknown")
        relative_path = file_metadata.get("file_path", file_path)

        instruction = (
            "Summarize this source file in about 100 words. "
            "Focus on the file's purpose, major components, and notable behavior. "
            "Keep the summary concise and useful for code search and QA."
        )

        prompt = f"File: {relative_path}\nLanguage: {language}\n\n{content}"

        # Synchronous retry loop on rate-limit errors. Configurable via env vars:
        max_retries = int(os.getenv("GEMINI_SUMMARY_RATE_LIMIT_RETRIES", "5"))
        wait_seconds = int(os.getenv("GEMINI_RATE_LIMIT_WAIT_SECONDS", "60"))

        attempts = 0
        while True:
            try:
                response = self.summary_client.generate_summary(prompt, instruction=instruction)
                return response.text.strip()
            except Exception as exc:
                attempts += 1
                msg = str(exc)
                # Detect obvious rate-limit/quota indicators in the error message
                is_rate_limit = any(k in msg.lower() for k in ("429", "too many requests", "quota", "resource_exhausted"))

                if is_rate_limit:
                    if attempts > max_retries:
                        self._log.warning(
                            "stage=summary_failed file=%s error=%s attempts=%d",
                            relative_path,
                            msg,
                            attempts,
                        )
                        return ""

                    self._log.warning(
                        "stage=summary_rate_limited file=%s attempt=%d waiting_seconds=%d",
                        relative_path,
                        attempts,
                        wait_seconds,
                    )
                    try:
                        time.sleep(wait_seconds)
                    except KeyboardInterrupt:
                        # Allow graceful interrupt during manual runs
                        self._log.info("stage=summary_sleep_interrupted file=%s", relative_path)
                        return ""
                    continue

                # Non-rate-limit error: log and move on
                self._log.warning("stage=summary_failed file=%s error=%s", relative_path, msg)
                return ""