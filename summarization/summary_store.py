import json
from pathlib import Path


SUMMARY_DIR = Path("data/summaries")


class SummaryStore:

    @staticmethod
    def _path(repo_name: str) -> Path:
        return SUMMARY_DIR / f"{repo_name}.json"

    @staticmethod
    def exists(repo_name: str) -> bool:
        return SummaryStore._path(repo_name).exists()

    @staticmethod
    def save(repo_name: str, summaries: dict[str, str]) -> None:
        path = SummaryStore._path(repo_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summaries, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def load(repo_name: str) -> dict[str, str]:
        path = SummaryStore._path(repo_name)
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def get(repo_name: str, file_path: str) -> str | None:
        summaries = SummaryStore.load(repo_name)
        return summaries.get(file_path)
