from ingestion.file_scanner import FileScanner
from ingestion.github_api_fetcher import GitHubAPIFetcher


class IngestionPipeline:

    def __init__(self):
        self.fetcher = GitHubAPIFetcher()
        self.scanner = FileScanner()

    def ingest(self, repo_url: str):
        """Clone + scan. Returns ``(files, repo_dir)`` — the clone path so the
        caller can read the commit SHA and clean up the unique per-run dir."""
        print("Cloning repository...")
        repo_path = self.fetcher.fetch_repo(repo_url)
        print("Scanning repository files...")
        files = self.scanner.scan_repository(repo_path)
        for f in files:
            f["repo_url"] = repo_url
        print(f"Discovered {len(files)} code files")
        return files, repo_path
