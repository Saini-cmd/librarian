from bootstrap import ensure_repo_root

ensure_repo_root()

from ingestion.ingestion_pipeline import IngestionPipeline

REPOS = [
    # "https://github.com/tiangolo/fastapi",
    # "https://github.com/pallets/flask",
    "https://github.com/psf/requests",
]

def main():
    ingestion = IngestionPipeline()

    for repo_url in REPOS:
        print(f"\nIngesting: {repo_url}")
        files, _repo_dir = ingestion.ingest(repo_url)
        print(f"Total files: {len(files)}")


if __name__ == "__main__":
    main()
