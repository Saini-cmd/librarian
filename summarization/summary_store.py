from backend.database import SessionLocal
from backend.models import FileSummary


class SummaryStore:

    @staticmethod
    def exists(repo_hash: str) -> bool:
        db = SessionLocal()
        try:
            return (
                db.query(FileSummary)
                .filter(FileSummary.repo_hash == repo_hash)
                .first()
                is not None
            )
        finally:
            db.close()

    @staticmethod
    def save(repo_hash: str, summaries: dict[str, str]) -> None:
        db = SessionLocal()
        try:
            db.query(FileSummary).filter(FileSummary.repo_hash == repo_hash).delete()
            for file_path, summary_text in summaries.items():
                db.add(
                    FileSummary(
                        repo_hash=repo_hash,
                        file_path=file_path,
                        summary_text=summary_text,
                    )
                )
            db.commit()
        finally:
            db.close()

    @staticmethod
    def load(repo_hash: str) -> dict[str, str]:
        db = SessionLocal()
        try:
            rows = (
                db.query(FileSummary)
                .filter(FileSummary.repo_hash == repo_hash)
                .all()
            )
            return {row.file_path: row.summary_text for row in rows}
        finally:
            db.close()

    @staticmethod
    def get(repo_hash: str, file_path: str) -> str | None:
        db = SessionLocal()
        try:
            row = (
                db.query(FileSummary)
                .filter(
                    FileSummary.repo_hash == repo_hash,
                    FileSummary.file_path == file_path,
                )
                .first()
            )
            return row.summary_text if row else None
        finally:
            db.close()
