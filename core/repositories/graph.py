"""Symbol-graph persistence (one graph per repo commit)."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.models import RepoGraph


def save_repo_graph(db: Session, repo_hash: str, graph: dict) -> None:
    row = db.query(RepoGraph).filter(RepoGraph.repo_hash == repo_hash).first()
    if row is None:
        row = RepoGraph(repo_hash=repo_hash, graph_json=graph)
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            # Concurrent graph save for the same commit won the INSERT — merge into it.
            db.rollback()
            row = db.query(RepoGraph).filter(RepoGraph.repo_hash == repo_hash).first()
            if row is not None:
                row.graph_json = graph
                db.commit()
    else:
        row.graph_json = graph
        db.commit()


def load_repo_graph(db: Session, repo_hash: str) -> dict | None:
    row = db.query(RepoGraph).filter(RepoGraph.repo_hash == repo_hash).first()
    return row.graph_json if row is not None else None


def delete_all_repo_graphs(db: Session) -> None:
    db.query(RepoGraph).delete()
    db.commit()
