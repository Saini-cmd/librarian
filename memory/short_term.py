"""Short-term memory read-path assembly.

Builds the conversation-history portion of the chat prompt from PostgreSQL:
last-N raw turns, falling back to the stored rolling summary when the raw
history exceeds the token budget.
"""

import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

from core.repositories.conversations import list_recent_messages, load_conversation_summary
from memory.store import MemoryStore, get_memory_store
from rag.context_builder import ContextBuilder


load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_MAX_TURNS = int(os.getenv("MEMORY_HISTORY_TURNS", "10"))
DEFAULT_TOKEN_BUDGET = int(os.getenv("MEMORY_HISTORY_TOKENS", "6000"))
DEFAULT_RECENT_TURNS = 4  # user/assistant pairs kept raw when the summary covers the rest
DEFAULT_MEMORY_TOP_K = int(os.getenv("MEMORY_TOP_K", "5"))


@dataclass(frozen=True)
class HistoryContext:
    messages: list[dict[str, str]]  # role/content, oldest → newest
    summary: str | None = None
    total_tokens: int = 0


def build_history(
    db,
    conversation_id,
    max_turns: int = DEFAULT_MAX_TURNS,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    recent_turns: int = DEFAULT_RECENT_TURNS,
) -> HistoryContext:
    """Assemble short-term history: raw turns, plus the rolling summary fallback."""
    rows = list_recent_messages(db, conversation_id, limit=max_turns)
    messages = [{"role": r.role, "content": r.content} for r in rows]
    total_tokens = sum(ContextBuilder._estimate_tokens(m["content"]) for m in messages)

    summary: str | None = None
    if total_tokens > token_budget:
        summary_row = load_conversation_summary(db, conversation_id)
        if summary_row:
            summary = summary_row.summary_content
            # Keep only the most recent turns raw; the summary covers everything older.
            if recent_turns and len(messages) > recent_turns * 2:
                messages = messages[-(recent_turns * 2):]

    logger.info(
        "stage=short_term turns=%d tokens=%d summary=%s",
        len(messages),
        total_tokens,
        bool(summary),
    )
    return HistoryContext(messages=messages, summary=summary, total_tokens=total_tokens)


def build_memory_context(
    db,
    conversation_id,
    clerk_id: str,
    repo_url: str | None,
    query: str,
    max_turns: int = DEFAULT_MAX_TURNS,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    memory_top_k: int = DEFAULT_MEMORY_TOP_K,
    store: MemoryStore | None = None,
) -> tuple[HistoryContext, list[str]]:
    """Assemble short-term history + long-term memory raw texts (zero-LLM).

    Long-term retrieval is best-effort: any failure degrades to no memory
    rather than breaking the chat request. Memory is scoped by `repo_url` so it
    survives a sync (repo_url is stable across commits).
    """
    history = build_history(db, conversation_id, max_turns=max_turns, token_budget=token_budget)

    memory_texts: list[str] = []
    if clerk_id and query:
        try:
            store = store or get_memory_store()
            hits = store.search(
                query,
                clerk_id=clerk_id,
                repo_url=repo_url,
                exclude_conversation_id=conversation_id,
                top_k=memory_top_k,
            )
            memory_texts = [h["text"] for h in hits if h.get("text")]
        except Exception:
            logger.exception("stage=long_term_memory retrieval failed; degrading to no memory")
            memory_texts = []

    logger.info(
        "stage=read_path history_turns=%d history_summary=%s memory=%d",
        len(history.messages),
        bool(history.summary),
        len(memory_texts),
    )
    return history, memory_texts
