"""Repo URL canonicalization — the single place that knows about URL forms."""

from urllib.parse import urlparse


def normalize_repo_url(repo_url: str) -> str:
    """Canonicalize a repo URL into a single identity form.

    Handles scp-style (git@host:owner/repo.git), ssh://, and http(s);
    strips trailing '.git' and '/'; lowercases the host. The canonical value is
    threaded through probing, cloning, storage, and lookups.
    """
    url = repo_url.strip()
    if not url:
        return ""

    if "://" not in url and "@" in url and ":" in url:
        host, _, path = url.partition(":")
        url = f"https://{host.removeprefix('git@')}/{path}"

    parsed = urlparse(url)
    scheme = "https" if parsed.scheme in ("", "ssh") else parsed.scheme
    host = parsed.hostname or ""
    path = parsed.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return f"{scheme}://{host}{path}"
