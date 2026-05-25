from ingestion.repo_cloner import RepoCloner
from ingestion.file_scanner import FileScanner

class IngestionPipeline:

    def __init__(self):
        self.cloner = RepoCloner()
        self.scanner = FileScanner()

    def ingest(self, repo_url: str):
        print("Starting ingestion...")
        repo_path = self.cloner.clone_repo(repo_url)
        print("Scanning repository files...")
        files = self.scanner.scan_repository(repo_path)
        print(f"Discovered {len(files)} code files")
        return files