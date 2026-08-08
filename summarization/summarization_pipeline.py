import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict

from tqdm import tqdm

from summarization.file_summarizer import FileSummarizer
from summarization.summary_store import SummaryStore


logger = logging.getLogger(__name__)
_MAX_WORKERS = 5


class SummarizationPipeline:

    def __init__(self):
        self.summarizer = FileSummarizer()

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
                executor.submit(self.summarizer.summarize_file, abs_path, lang): rel_path
                for rel_path, (abs_path, lang) in unique_files.items()
            }

            for future in tqdm(as_completed(future_map), total=total, desc="Summarizing"):
                rel_path = future_map[future]
                try:
                    summary = future.result()
                    if summary:
                        summaries[rel_path] = summary
                except Exception:
                    logger.warning("Failed to summarize %s, skipping", rel_path)

        SummaryStore.save(repo_hash, summaries)
        logger.info("Summarized %d/%d files for %s", len(summaries), total, repo_hash)
        return summaries
