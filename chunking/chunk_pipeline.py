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
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from dataclasses import asdict
from typing import List, Dict

from chunking.ast_chunker import ASTChunker
from chunking.chunk_model import CodeChunk
from chunking.text_chunker import TextChunker
from rag.external.llm.deepseek_client import DeepSeekClient
from rag.local.llm.local_summary_client import LocalSummaryClient
from tqdm import tqdm

SUMMARY_MAX_CHARS = int(os.getenv("DEEPSEEK_SUMMARY_MAX_CHARS", "12000"))
SUMMARY_BATCH_SIZE = int(os.getenv("DEEPSEEK_SUMMARY_BATCH_SIZE", "50"))
SUMMARY_BATCH_WORKERS = int(os.getenv("DEEPSEEK_SUMMARY_BATCH_WORKERS", "8"))


@lru_cache(maxsize=1)
def _get_summary_client() -> DeepSeekClient:
    provider = os.getenv("SUMMARY_PROVIDER", "external").strip().lower()
    if provider == "local":
        return LocalSummaryClient()
    return DeepSeekClient()


class ChunkPipeline:
    def __init__(self):
        self.summary_client = _get_summary_client()
        self._log = logging.getLogger(__name__)
        self.ast_chunker = ASTChunker()
        self.text_chunker = TextChunker()

    def chunk_repository(self, files_metadata: List[Dict], repo_name: str) -> List[CodeChunk]:
        """
        Chunk all files, collect per‑file summaries, save summaries to JSON,
        and return chunks (without summary attached to each chunk).
        """
        all_chunks: List[CodeChunk] = []
        files = list(files_metadata)

        if not files:
            self._save_chunks(repo_name, all_chunks)
            self._save_summaries(repo_name, {})  # empty summary file
            return all_chunks

        # Dictionary to store summaries keyed by relative file path
        file_summaries: Dict[str, str] = {}

        for batch_start in range(0, len(files), SUMMARY_BATCH_SIZE):
            batch = files[batch_start:batch_start + SUMMARY_BATCH_SIZE]
            batch_number = batch_start // SUMMARY_BATCH_SIZE + 1

            # Get summaries for this batch (returns dict keyed by batch index)
            batch_summaries = self._summarize_files_batch(batch, batch_number=batch_number)

            for idx, file_metadata in enumerate(batch):
                file_metadata["repo"] = repo_name
                processing_type = file_metadata.get("processing_type", "text")
                file_path = file_metadata.get("file_path", "")
                file_summary = batch_summaries.get(idx, "")

                # Store summary keyed by relative path for later JSON export
                if file_path and file_summary:
                    file_summaries[file_path] = file_summary

                try:
                    if processing_type == "ast":
                        chunks = self.ast_chunker.chunk_file(file_metadata)
                        if chunks:
                            print(f"DEBUG: First chunk repo after chunker: '{chunks[0].repo}'")

                    else:  # "text"
                        chunks = self.text_chunker.chunk_file(file_metadata)
                        if chunks:
                            print(f"DEBUG: First chunk repo after chunker: '{chunks[0].repo}'")

                    # Do NOT attach summary to each chunk (old logic removed)
                    all_chunks.extend(chunks)

                except Exception:
                    traceback.print_exc()
                    continue

        # Save chunks (without summaries) and the summary JSON
        self._save_chunks(repo_name, all_chunks)
        self._save_summaries(repo_name, file_summaries)

        return all_chunks

    def _summarize_files_batch(self, files_batch: List[Dict], batch_number: int) -> Dict[int, str]:
        """
        Generate summaries for a batch of files in parallel.
        Returns dict mapping batch index -> summary text (empty string on failure).
        """
        summaries: Dict[int, str] = {}

        if not files_batch:
            return summaries

        max_workers = max(1, min(SUMMARY_BATCH_WORKERS, len(files_batch)))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._summarize_file, file_metadata): index
                for index, file_metadata in enumerate(files_batch)
            }

            try:
                for future in tqdm(as_completed(futures), total=len(futures), desc=f"Summaries batch {batch_number}"):
                    index = futures[future]
                    try:
                        summaries[index] = future.result()
                    except Exception:
                        summaries[index] = ""
            except KeyboardInterrupt:
                for future in futures:
                    future.cancel()
                raise

        return summaries

    def _summarize_file(self, file_metadata: Dict) -> str:
        """
        Generate a summary for a single file using the configured LLM client.
        Returns empty string if summarisation fails or is disabled.
        """
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

        instruction = """Analyze the following source code and produce a retrieval-optimized summary in no more than 100 words.

Include:
- File purpose.
- Main classes, functions, and exported symbols.
- Business logic and responsibilities.
- External services, APIs, databases, or frameworks referenced.
- Key concepts a developer might search for when looking for this file.

Output only the summary text.
Maximum 100 words."""

        prompt = f"File: {relative_path}\nLanguage: {language}\n\n{content}"

        max_retries = int(os.getenv("DEEPSEEK_SUMMARY_RATE_LIMIT_RETRIES", "5"))
        wait_seconds = int(os.getenv("DEEPSEEK_SUMMARY_RATE_LIMIT_WAIT_SECONDS", "60"))

        attempts = 0
        while True:
            try:
                response = self.summary_client.generate_summary(prompt, instruction=instruction)
                return response.text.strip()
            except Exception as exc:
                attempts += 1
                msg = str(exc)
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
                        self._log.info("stage=summary_sleep_interrupted file=%s", relative_path)
                        return ""
                    continue

                # Non-rate-limit error
                self._log.warning("stage=summary_failed file=%s error=%s", relative_path, msg)
                return ""

    def _save_chunks(self, repo_name: str, chunks: List[CodeChunk]) -> None:
        """Save chunks as a pickle file."""
        try:
            chunks_dir = Path("data/chunks")
            chunks_dir.mkdir(parents=True, exist_ok=True)

            output_path = chunks_dir / f"{repo_name}.pkl"
            temp_path = output_path.with_suffix(".pkl.tmp")

            # Convert to dict for serialization (summary field may still exist but will be empty)
            serializable_chunks = [asdict(chunk) for chunk in chunks]

            with open(temp_path, "wb") as f:
                pickle.dump(serializable_chunks, f)

            temp_path.replace(output_path)
            print(f"\nSaved {len(chunks)} chunks → {output_path}")

        except Exception:
            print("Failed to save chunks")
            traceback.print_exc()

    def _save_summaries(self, repo_name: str, file_summaries: Dict[str, str]) -> None:
        """
        Save per‑file summaries to data/summary/<repo_name>.json.
        The JSON is a dict: { "relative/file/path.py": "summary text", ... }
        """
        try:
            summary_dir = Path("data/summary")
            summary_dir.mkdir(parents=True, exist_ok=True)

            output_path = summary_dir / f"{repo_name}.json"
            temp_path = output_path.with_suffix(".json.tmp")

            import json
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(file_summaries, f, indent=2, ensure_ascii=False)

            temp_path.replace(output_path)
            print(f"Saved {len(file_summaries)} file summaries → {output_path}")

        except Exception:
            print("Failed to save summaries")
            traceback.print_exc()