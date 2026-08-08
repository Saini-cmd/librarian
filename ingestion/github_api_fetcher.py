import logging
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse


logger = logging.getLogger(__name__)


class GitHubAPIFetcher:
    """Clones a GitHub repo via git (shallow, depth=1) — no PyGithub REST calls."""

    def __init__(self, base_dir: str = "data/repos", token: str | None = None):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.token = token or os.getenv("GITHUB_TOKEN")

    def fetch_repo(self, repo_url: str, force: bool = False) -> Path:
        owner, name = self._parse_repo_url(repo_url)
        repo_path = self.base_dir / name

        if repo_path.exists():
            if not force:
                logger.info("Repository directory already exists: %s", repo_path)
                return repo_path
            logger.info("Force re-clone: removing existing %s", repo_path)
            shutil.rmtree(repo_path)

        clone_url = self._auth_url(repo_url)
        logger.info("Cloning %s/%s with depth=1...", owner, name)

        result = subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, str(repo_path)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"git clone failed for {repo_url}: {result.stderr.strip()}"
            )

        logger.info("Cloned %s/%s into %s", owner, name, repo_path)
        return repo_path

    @staticmethod
    def head_sha(repo_path: Path) -> str:
        """Return the current HEAD commit SHA of a cloned repo (works on shallow clones)."""
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"git rev-parse HEAD failed for {repo_path}: {result.stderr.strip()}"
            )
        return result.stdout.strip()

    def remote_head_sha(self, repo_url: str) -> str:
        """Return the remote HEAD SHA without cloning (git ls-remote).

        Used as the cheap change probe before deciding to (re)ingest.
        """
        auth_url = self._auth_url(repo_url)
        result = subprocess.run(
            ["git", "ls-remote", auth_url, "HEAD"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"git ls-remote failed for {repo_url}: {result.stderr.strip()}"
            )
        if not result.stdout.strip():
            raise RuntimeError(f"No HEAD ref found for {repo_url}")
        return result.stdout.strip().split()[0]

    def _auth_url(self, raw_url: str) -> str:
        """Inject GITHUB_TOKEN into the URL for authenticated cloning."""
        if not self.token:
            return raw_url
        parsed = urlparse(raw_url)
        return f"https://x-access-token:{self.token}@{parsed.hostname}{parsed.path}"

    @staticmethod
    def _parse_repo_url(repo_url: str) -> tuple[str, str]:
        parsed = urlparse(repo_url.strip())
        parts = parsed.path.strip("/").split("/")
        if len(parts) < 2:
            raise ValueError(f"Could not parse owner/repo from URL: {repo_url}")
        owner = parts[-2]
        name = parts[-1]
        if name.endswith(".git"):
            name = name[:-4]
        return owner, name
