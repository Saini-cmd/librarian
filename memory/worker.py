"""ARQ background worker for chat-memory maintenance.

Jobs:
- `vectorize_exchange` — embed a (user, assistant) exchange into `long_term_memory`.
- `rollup_session_summary` — merge messages newer than the summary watermark into
  the rolling `conversation_summaries` row, using the shared OpenRouter
  summarization model (`SUMMARIZE_*` config).

Run with: `venv/bin/arq memory.worker.WorkerSettings`
"""

import asyncio
import logging
import os

from arq.connections import RedisSettings, create_pool
from dotenv import load_dotenv

from backend.database import SessionLocal
from memory.store import MemoryStore
from rag.context_builder import ContextBuilder


load_dotenv()

logger = logging.getLogger(__name__)

SUMMARIZE_DEFER_SECONDS = int(os.getenv("MEMORY_SUMMARIZE_DEFER_SECONDS", "60"))
SUMMARIZE_EVERY = int(os.getenv("MEMORY_SUMMARIZE_EVERY", "10"))
_SUMMARIZE_INPUT_TOKEN_BUDGET = 8000


def _redis_settings() -> RedisSettings:
    dsn = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return RedisSettings.from_dsn(dsn)


def enqueue_memory_jobs(
    conversation_id,
    user_message_id,
    assistant_message_id,
    clerk_id: str,
    repo_url: str | None = None,
    repo_hash: str | None = None,
) -> None:
    """Fire-and-forget enqueue of background memory jobs. Never raises — Redis down
    degrades to no-memory, never breaks the chat request.
    """

    async def _go() -> None:
        pool = await create_pool(WorkerSettings.redis_settings)
        try:
            await pool.enqueue_job(
                "vectorize_exchange",
                conversation_id=str(conversation_id),
                user_message_id=str(user_message_id),
                assistant_message_id=str(assistant_message_id) if assistant_message_id else None,
                clerk_id=clerk_id,
                repo_url=repo_url,
                repo_hash=repo_hash,
            )
            await pool.enqueue_job(
                "rollup_session_summary",
                conversation_id=str(conversation_id),
                _defer_by=SUMMARIZE_DEFER_SECONDS,
            )
        finally:
            await pool.aclose()

    try:
        asyncio.run(_go())
    except Exception:
        logger.exception("Failed to enqueue memory jobs (Redis down?)")


async def vectorize_exchange(
    ctx,
    conversation_id,
    user_message_id,
    assistant_message_id,
    clerk_id,
    repo_url: str | None = None,
    repo_hash: str | None = None,
) -> None:
    """Embed `"User: ... | Assistant: ..."` into long-term memory (idempotent)."""

    def _run() -> None:
        db = SessionLocal()
        try:
            from backend.models import Conversation, Message

            user_msg = db.get(Message, user_message_id)
            if user_msg is None:
                logger.warning("vectorize_exchange: user message %s not found", user_message_id)
                return
            text = f"User: {user_msg.content}"
            if assistant_message_id is not None:
                assistant_msg = db.get(Message, assistant_message_id)
                if assistant_msg is not None:
                    text += f" | Assistant: {assistant_msg.content}"
            if repo_url is None:
                conv = db.get(Conversation, conversation_id)
                if conv is not None and conv.indexed_repo is not None:
                    resolved_url = conv.indexed_repo.repo_url
                else:
                    resolved_url = None
            else:
                resolved_url = repo_url
            MemoryStore().upsert_exchange(
                clerk_id=clerk_id,
                repo_url=resolved_url,
                repo_hash=repo_hash,
                conversation_id=conversation_id,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
                text=text,
            )
            logger.info("vectorized exchange %s -> %s", conversation_id, user_message_id)
        finally:
            db.close()

    await asyncio.to_thread(_run)


async def rollup_session_summary(ctx, conversation_id) -> None:
    """Merge new messages into the rolling conversation summary.

    Gated: summarizes only once at least `SUMMARIZE_EVERY` new messages have
    accumulated since the watermark (deferred enqueues keep re-firing until then).
    Runs the shared OpenRouter summarization model in a worker thread.
    """

    def _run() -> None:
        db = SessionLocal()
        try:
            from backend.state import (
                load_conversation_summary,
                messages_since,
                save_conversation_summary,
            )

            row = load_conversation_summary(db, conversation_id)
            watermark_id = row.last_message_id if row else None

            new_messages = messages_since(db, conversation_id, after_message_id=watermark_id)
            if len(new_messages) < SUMMARIZE_EVERY:
                logger.info(
                    "rollup skip conversation=%s new=%d < %d",
                    conversation_id, len(new_messages), SUMMARIZE_EVERY,
                )
                return

            selected = _cap_input_tokens(new_messages)
            existing = row.summary_content if row else None
            summary_text = _summarize(selected, existing)

            tokens_covered = sum(
                ContextBuilder._estimate_tokens(m.content) for m in selected
            )
            total = (row.total_tokens_covered if row else 0) + tokens_covered
            save_conversation_summary(
                db,
                conversation_id,
                summary_text,
                total_tokens_covered=total,
                last_message_id=selected[-1].id,
            )
            logger.info(
                "rollup saved conversation=%s summarized=%d/%d watermark=%s",
                conversation_id, len(selected), len(new_messages), selected[-1].id,
            )
        finally:
            db.close()

    await asyncio.to_thread(_run)


def _cap_input_tokens(messages, budget: int = _SUMMARIZE_INPUT_TOKEN_BUDGET):
    """Keep the most recent messages that fit the input token budget (≥1 message)."""
    total = 0
    kept: list = []
    for message in reversed(messages):
        tokens = ContextBuilder._estimate_tokens(message.content)
        if kept and total + tokens > budget:
            break
        kept.append(message)
        total += tokens
    kept.reverse()
    return kept or [messages[-1]]


def _format_messages(messages) -> str:
    return "\n".join(
        f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}" for m in messages
    )


def _summarize(messages, existing_summary: str | None) -> str:
    """Summarize (or merge into) the rolling summary via the shared OpenRouter model."""
    from prompts import (
        MEMORY_ROLLUP_FRESH_SYSTEM_PROMPT,
        MEMORY_ROLLUP_MERGE_SYSTEM_PROMPT,
        memory_rollup_user_prompt,
    )
    from rag.llm_client import LLMClient
    from summarization.llm_config import build_summarizer_config

    client = LLMClient(build_summarizer_config())
    if existing_summary:
        system = MEMORY_ROLLUP_MERGE_SYSTEM_PROMPT
    else:
        system = MEMORY_ROLLUP_FRESH_SYSTEM_PROMPT
    user_content = memory_rollup_user_prompt(
        existing_summary, _format_messages(messages)
    )

    response = client.generate(
        [{"role": "system", "content": system}, {"role": "user", "content": user_content}],
        stream=False,
    )
    text = response.text.strip()
    return text or existing_summary or ""


class WorkerSettings:
    functions = [vectorize_exchange, rollup_session_summary]
    redis_settings = _redis_settings()
    max_jobs = 4
    job_timeout = 300