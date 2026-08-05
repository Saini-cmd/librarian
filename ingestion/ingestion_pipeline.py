from ingestion.file_scanner import FileScanner
from ingestion.github_api_fetcher import GitHubAPIFetcher


class IngestionPipeline:

    def __init__(self):
        self.fetcher = GitHubAPIFetcher()
        self.scanner = FileScanner()

    def ingest(self, repo_url: str):
        _, repo_name = GitHubAPIFetcher._parse_repo_url(repo_url)
        print("Cloning repository...")
        repo_path = self.fetcher.fetch_repo(repo_url)
        print("Scanning repository files...")
        files = self.scanner.scan_repository(repo_path)
        for f in files:
            f["repo"] = repo_name
        print(f"Discovered {len(files)} code files")
        return files
