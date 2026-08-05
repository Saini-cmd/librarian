import json
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from vector_store.qdrant_client import QdrantManager


INDEX_STATE_FILE = Path("data/chunks/index_state.json")
REPO_MARKER_FILE = Path("data/chunks/repo_marker.txt")
QA_RESPONSE_FILE = Path("data/responses/latest.md")


def repo_name_from_url(repo_url: str) -> str:
    parsed = urlparse(repo_url.strip())
    name = Path(parsed.path).name
    return name[:-4] if name.endswith(".git") else name or "repo"


def collection_exists(collection_name: str = "code_chunks") -> bool:
    client = QdrantManager().get_client()
    collections = client.get_collections().collections
    return any(c.name == collection_name for c in collections)


def repo_marker_matches(repo_name: str) -> bool:
    if not REPO_MARKER_FILE.exists():
        return False
    try:
        return REPO_MARKER_FILE.read_text(encoding="utf-8").strip() == repo_name
    except Exception:
        return False


def write_repo_marker(repo_name: str) -> None:
    try:
        REPO_MARKER_FILE.parent.mkdir(parents=True, exist_ok=True)
        REPO_MARKER_FILE.write_text(repo_name.strip(), encoding="utf-8")
    except Exception:
        pass


def write_index_state(repo_name: str, files_discovered: int, chunks_created: int) -> None:
    try:
        INDEX_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        INDEX_STATE_FILE.write_text(
            json.dumps(
                {"repo_name": repo_name, "files_discovered": files_discovered, "chunks_created": chunks_created},
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass


def write_qa_markdown(repo_name: str, query: str, answer: str, citations: list[dict[str, Any]]) -> None:
    try:
        QA_RESPONSE_FILE.parent.mkdir(parents=True, exist_ok=True)
        citation_lines = [
            f"- [{c.get('citation_id', '')}] {c.get('file_path', '')}:{c.get('start_line', '')}-{c.get('end_line', '')}"
            for c in citations if c
        ]
        md = [
            f"# QA Response",
            f"- Repo: {repo_name}",
            "",
            "## Question",
            query,
            "",
            "## Answer",
            answer,
        ]
        if citation_lines:
            md.extend(["", "## Citations", *citation_lines])
        QA_RESPONSE_FILE.write_text("\n".join(md).rstrip() + "\n", encoding="utf-8")
    except Exception:
        pass


def reset_index_state(wipe: bool = True) -> None:
    if wipe:
        try:
            if collection_exists():
                QdrantManager().get_client().delete_collection("code_chunks")
        except Exception:
            pass

        chunks_dir = Path("data/chunks")
        if chunks_dir.exists():
            shutil.rmtree(chunks_dir, ignore_errors=True)

        for file_path in [REPO_MARKER_FILE, INDEX_STATE_FILE, QA_RESPONSE_FILE]:
            if file_path.exists():
                file_path.unlink()
