from bootstrap import ensure_repo_root

ensure_repo_root()

from pathlib import Path

from ingestion.github_api_fetcher import GitHubAPIFetcher
from ingestion.ingestion_pipeline import IngestionPipeline
from summarization.summarization_pipeline import SummarizationPipeline
from summarization.summary_store import SummaryStore


REPOS = [
    "https://github.com/psf/requests",
]


def main():
    ingestion = IngestionPipeline()
    summarizer = SummarizationPipeline()

    for repo_url in REPOS:
        name = repo_url.removesuffix(".git").split("/")[-1]
        print(f"\nProcessing: {repo_url}")

        files = ingestion.ingest(repo_url)
        repo_hash = GitHubAPIFetcher.head_sha(Path("data/repos") / name)
        summaries = summarizer.summarize(files, repo_hash)

        print(f"Total files      : {len(files)}")
        print(f"Files summarized : {len(summaries)}")

        assert SummaryStore.exists(repo_hash), "Summary file should exist"
        loaded = SummaryStore.load(repo_hash)
        assert len(loaded) == len(summaries), "Saved summaries should match"

        if summaries:
            sample_path = next(iter(summaries))
            sample_summary = summaries[sample_path]
            print(f"\nSample summary for {sample_path}:")
            print(f"  {sample_summary[:200]}...")


if __name__ == "__main__":
    main()
