import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict

from tqdm import tqdm

from summarization.file_summarizer import FileSummarizer
from summarization.summary_store import SummaryStore


logger = logging.getLogger(__name__)

# Transient LLM failures (e.g. OpenRouter 429 rate limiting on the cheap
# summarization model) are retried with exponential backoff so stragglers
# finish instead of being dropped. Both knobs are env-configurable.
_MAX_WORKERS = int(os.getenv("SUMMARIZE_CONCURRENCY", "5"))
_MAX_ATTEMPTS = int(os.getenv("SUMMARIZE_MAX_ATTEMPTS", "3"))
_BASE_DELAY = 2.0  # seconds; backoff = base * 2**attempt


class SummarizationPipeline:

    def __init__(self):
        self.summarizer = FileSummarizer()

    def _summarize_with_retry(self, abs_path: str, lang: str) -> str:
        """`summarize_file` with exponential backoff on transient failure.

        Raises after `_MAX_ATTEMPTS` attempts so the caller can log the final
        failure (with traceback) once, instead of skipping the first blip.
        """
        last_error: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                return self.summarizer.summarize_file(abs_path, lang)
            except Exception as exc:
                last_error = exc
                if attempt < _MAX_ATTEMPTS - 1:
                    delay = _BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "Summarize failed for %s (attempt %d/%d, %s); retrying in %.1fs",
                        abs_path,
                        attempt + 1,
                        _MAX_ATTEMPTS,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
        raise RuntimeError(
            f"summarize failed after {_MAX_ATTEMPTS} attempts"
        ) from last_error

    def summarize(self, files_metadata: List[Dict], repo_hash: str) -> dict[str, str]:
        if SummaryStore.exists(repo_hash):
            logger.info("Summaries already exist for %s, skipping", repo_hash)
            return SummaryStore.load(repo_hash)

        unique_files = {
            meta["file_path"]: (meta["absolute_path"], meta.get("language", "unknown"))
            for meta in files_metadata
        }

        summaries: dict[str, str] = {}
        total = len(unique_files)
        logger.info("Summarizing %d files for %s...", total, repo_hash)

        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
            future_map = {
                executor.submit(self._summarize_with_retry, abs_path, lang): rel_path
                for rel_path, (abs_path, lang) in unique_files.items()
            }

            for future in tqdm(as_completed(future_map), total=total, desc="Summarizing"):
                rel_path = future_map[future]
                try:
                    summary = future.result()
                    if summary:
                        summaries[rel_path] = summary
                except Exception:
                    logger.warning(
                        "Failed to summarize %s after %d attempts, skipping",
                        rel_path,
                        _MAX_ATTEMPTS,
                        exc_info=True,
                    )

        SummaryStore.save(repo_hash, summaries)
        logger.info("Summarized %d/%d files for %s", len(summaries), total, repo_hash)
        return summaries
