from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from backend.models import (
    Conversation,
    FileSummary,
    Message,
    PipelineState,
    QaRecord,
    RepoGraph,
    User,
    UserRepo,
)
from vector_store.qdrant_client import QdrantManager


COLLECTION_NAME = "code_chunks"


def repo_name_from_url(repo_url: str) -> str:
    parsed = urlparse(repo_url.strip())
    name = Path(parsed.path).name
    return name[:-4] if name.endswith(".git") else name or "repo"


def default_conversation_title(repo_name: str | None = None) -> str:
    ts = datetime.now().strftime("%b %d, %H:%M:%S")
    return f"{repo_name} · {ts}" if repo_name else f"Chat · {ts}"


def collection_exists(collection_name: str = COLLECTION_NAME) -> bool:
    try:
        client = QdrantManager().get_client()
        collections = client.get_collections().collections
        return any(c.name == collection_name for c in collections)
    except Exception:
        return False


# ---- Pipeline state (replaces APP_STATE + marker/index files) ----


def get_pipeline_state(db: Session) -> PipelineState:
    state = db.get(PipelineState, 1)
    if state is None:
        state = PipelineState(id=1)
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def update_pipeline_state(db: Session, **kwargs: Any) -> PipelineState:
    state = get_pipeline_state(db)
    for key, value in kwargs.items():
        setattr(state, key, value)
    db.commit()
    db.refresh(state)
    return state


def pipeline_state_dict(db: Session) -> dict[str, Any]:
    state = get_pipeline_state(db)
    return {
        "phase": state.phase,
        "progress": state.progress,
        "message": state.message,
        "stage": state.stage,
        "ready": state.ready,
        "indexed_repo_name": state.indexed_repo_name,
    }


# ---- Users / repos ----


def get_user_by_clerk_id(db: Session, clerk_id: str) -> User | None:
    return db.query(User).filter(User.clerk_id == clerk_id).first()


def upsert_user(db: Session, clerk_id: str, **fields: Any) -> User:
    user = get_user_by_clerk_id(db, clerk_id)
    if user is None:
        user = User(clerk_id=clerk_id, **fields)
        db.add(user)
    else:
        for key, value in fields.items():
            setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user


def user_repo_exists(db: Session, user_id: Any, repo_name: str) -> bool:
    return (
        db.query(UserRepo)
        .filter(UserRepo.user_id == user_id, UserRepo.repo_name == repo_name)
        .first()
        is not None
    )


def last_indexed_repo_for_user(db: Session, user_id: Any) -> str | None:
    repo = (
        db.query(UserRepo)
        .filter(UserRepo.user_id == user_id)
        .order_by(UserRepo.updated_at.desc())
        .first()
    )
    return repo.repo_name if repo else None


def record_user_repo(
    db: Session,
    user_id: Any,
    repo_name: str,
    repo_url: str,
    files_discovered: int,
    chunks_created: int,
    status: str = "indexed",
) -> UserRepo:
    repo = (
        db.query(UserRepo)
        .filter(UserRepo.user_id == user_id, UserRepo.repo_name == repo_name)
        .first()
    )
    if repo is None:
        repo = UserRepo(user_id=user_id, repo_name=repo_name, repo_url=repo_url)
        db.add(repo)
    repo.repo_url = repo_url
    repo.files_discovered = files_discovered
    repo.chunks_created = chunks_created
    repo.status = status
    db.commit()
    return repo


# ---- Conversations ----


def resolve_conversation_repo(
    db: Session,
    user_id: Any,
    conversation_id: Any,
    requested_repo: str | None,
) -> str | None:
    """Resolve the repo a chat should search over.

    Precedence: the conversation's stored repo (if continuing one) > the
    repo the client requested > the last globally indexed repo.
    """
    repo_name = requested_repo
    if conversation_id is not None:
        conv = db.get(Conversation, conversation_id)
        if conv is not None and conv.user_id == user_id and conv.repo_name:
            repo_name = conv.repo_name
    if not repo_name:
        repo_name = pipeline_state_dict(db).get("indexed_repo_name")
    return repo_name


def get_or_create_conversation(
    db: Session,
    user_id: Any,
    conversation_id: Any = None,
    title: str | None = None,
    repo_name: str | None = None,
    repo_url: str | None = None,
) -> Conversation:
    if conversation_id is not None:
        conv = db.get(Conversation, conversation_id)
        if conv is not None and conv.user_id == user_id:
            return conv
    conv = Conversation(
        user_id=user_id,
        title=title or default_conversation_title(repo_name),
        repo_name=repo_name,
        repo_url=repo_url,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def add_message(
    db: Session,
    conversation_id: Any,
    role: str,
    content: str,
    citations: list[dict] | None = None,
) -> Message:
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        citations=citations or [],
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


# ---- Summaries / QA ----


def save_qa_record(db: Session, repo_name: str, query: str, answer: str, citations: list[dict]) -> None:
    db.add(QaRecord(repo_name=repo_name, query=query, answer=answer, citations=citations))
    db.commit()


# ---- Repo graphs ----


def save_repo_graph(db: Session, repo_name: str, graph: dict) -> None:
    row = db.get(RepoGraph, repo_name)
    if row is None:
        row = RepoGraph(repo_name=repo_name, graph_json=graph)
        db.add(row)
    else:
        row.graph_json = graph
    db.commit()


def load_repo_graph(db: Session, repo_name: str) -> dict | None:
    row = db.get(RepoGraph, repo_name)
    return row.graph_json if row is not None else None


def delete_all_repo_graphs(db: Session) -> None:
    db.query(RepoGraph).delete()
    db.commit()


def reset_index_state(db: Session, wipe: bool = True) -> None:
    if wipe:
        try:
            if collection_exists(COLLECTION_NAME):
                QdrantManager().get_client().delete_collection(COLLECTION_NAME)
        except Exception:
            pass

    db.query(QaRecord).delete()
    db.query(FileSummary).delete()
    db.query(UserRepo).delete()
    db.query(RepoGraph).delete()
    db.query(PipelineState).delete()
    db.commit()
