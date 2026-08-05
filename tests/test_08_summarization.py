from bootstrap import ensure_repo_root

ensure_repo_root()

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
        summaries = summarizer.summarize(files, name)

        print(f"Total files      : {len(files)}")
        print(f"Files summarized : {len(summaries)}")

        assert SummaryStore.exists(name), "Summary file should exist"
        loaded = SummaryStore.load(name)
        assert len(loaded) == len(summaries), "Saved summaries should match"

        if summaries:
            sample_path = next(iter(summaries))
            sample_summary = summaries[sample_path]
            print(f"\nSample summary for {sample_path}:")
            print(f"  {sample_summary[:200]}...")


if __name__ == "__main__":
    main()
