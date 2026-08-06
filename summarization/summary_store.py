from backend.database import SessionLocal
from backend.models import FileSummary


class SummaryStore:

    @staticmethod
    def exists(repo_name: str) -> bool:
        db = SessionLocal()
        try:
            return (
                db.query(FileSummary)
                .filter(FileSummary.repo_name == repo_name)
                .first()
                is not None
            )
        finally:
            db.close()

    @staticmethod
    def save(repo_name: str, summaries: dict[str, str]) -> None:
        db = SessionLocal()
        try:
            db.query(FileSummary).filter(FileSummary.repo_name == repo_name).delete()
            for file_path, summary_text in summaries.items():
                db.add(
                    FileSummary(
                        repo_name=repo_name,
                        file_path=file_path,
                        summary_text=summary_text,
                    )
                )
            db.commit()
        finally:
            db.close()

    @staticmethod
    def load(repo_name: str) -> dict[str, str]:
        db = SessionLocal()
        try:
            rows = (
                db.query(FileSummary)
                .filter(FileSummary.repo_name == repo_name)
                .all()
            )
            return {row.file_path: row.summary_text for row in rows}
        finally:
            db.close()

    @staticmethod
    def get(repo_name: str, file_path: str) -> str | None:
        db = SessionLocal()
        try:
            row = (
                db.query(FileSummary)
                .filter(
                    FileSummary.repo_name == repo_name,
                    FileSummary.file_path == file_path,
                )
                .first()
            )
            return row.summary_text if row else None
        finally:
            db.close()
