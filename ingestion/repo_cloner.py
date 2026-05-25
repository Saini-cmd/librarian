from git import Repo
from pathlib import Path

class RepoCloner:

    def __init__(self, base_dir="data/repos"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def extract_repo_name(self, repo_url: str) -> str:
        return repo_url.rstrip("/").split("/")[-1].replace(".git", "")

    def clone_repo(self, repo_url: str) -> Path:
        repo_name = self.extract_repo_name(repo_url)
        repo_path = self.base_dir / repo_name

        if repo_path.exists():
            print(f"Repository already exists: {repo_name}")
            return repo_path

        print(f"Cloning repository {repo_name}...")
        Repo.clone_from(repo_url, repo_path)
        print("Clone completed")
        return repo_path