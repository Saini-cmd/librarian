# core/

## Purpose
Shared foundation package that both the API layer (`backend/`) and the domain packages (`ingestion/`, `orchestration/`, `summarization/`, `memory/`, `evaluation/`, …) depend on: DB engine/session, ORM models, data-access repositories, URL canonicalization, the usage-cap ledger, and the prompt-template single source.

**Layering rule (D39):** `core/` must never import from `backend/` or any domain package. `backend/` + the domain packages may import `core/`. This inverts the old layout where domain packages reached into `backend.state`/`backend.database`.

## Ownership
- `db.py` — Sync SQLAlchemy engine (`DATABASE_URL`, pool `DB_POOL_SIZE`/`DB_MAX_OVERFLOW`), `SessionLocal`, `Base`, `get_db`, `init_db` (create_all on startup)
- `models.py` — ORM models (9 tables): `User`, `IndexedRepo`, `FileSummary`, `RepoGraph`, `Conversation`, `Message`, `Citation`, `ConversationSummary`, `UsageEvent`
- `url.py` — `normalize_repo_url` (canonical repo URL identity)
- `usage.py` — **24h per-user usage caps**: `check_usage` (429 gate, pre-spend) / `record_usage` (post-spend append + per-user purge) / `usage_status`; action groups `ingest` (`USAGE_INGEST_MAX` — repo_ingest+repo_sync) and `message` (`USAGE_MESSAGE_MAX` — chat_message+explain); `0` = uncapped
- `prompts.py` — **Single source of truth for every LLM prompt template** (D32): RAG answer generation, file summarization, chat-memory rollups, node explanation, eval judges, golden-set paraphrase. Consumers (`rag/`, `summarization/`, `memory/`, `backend/routers`, `evaluation/`) import from here; keep prompt text in this file only
- `repositories/` — data-access helpers split from the old `backend/state.py`:
  - `users.py` — `get_user_by_clerk_id`, `upsert_user`
  - `indexed_repo.py` — `get_or_create_indexed_repo`, `indexed_repo_by_hash`, `ensure_repo_indexing`, `mark_repo_failed`, `latest_indexed_repo_by_url`, + user-repo derivation (`user_repo_urls`, `user_repo_exists`, `last_indexed_repo_for_user`, `list_user_repos`)
  - `conversations.py` — `resolve_conversation_repo`, `get_or_create_conversation`, `add_message`, `list_recent_messages`, `messages_since`, `default_conversation_title`, rolling summaries (`load/save_conversation_summary`), citations (`write_citations`, `cited_chunk_ids`)
  - `graph.py` — `save_repo_graph`, `load_repo_graph`, `delete_all_repo_graphs`
- `repositories/conversations.py` depends on `repositories/indexed_repo.py` (chat repo resolution); repositories otherwise depend only on `core.models` + `core.db`

## Local Contracts
- Session lifecycle: `SessionLocal` for short-lived self-managed sessions; `get_db` for request-scoped FastAPI dependency; helpers that open their own session (e.g. `ensure_repo_indexing`, `mark_repo_failed`, `record_usage`, `SummaryStore`) always `close()` in `finally`
- **Race-free get-or-create** (D23): `upsert_user`, `get_or_create_indexed_repo`, `ensure_repo_indexing`, `save_repo_graph`, `save_conversation_summary` catch `IntegrityError`, roll back, re-SELECT, and adopt/merge the concurrent winner
- **Identity = `repo_url` + `repo_hash`** (D22): `normalize_repo_url` is the single URL-form authority; Qdrant scoping is hash-only
- **Usage caps** (D37): Postgres `COUNT`s over `usage_events` in a rolling window — correct across workers, no Redis; soft boundary under races (bounded by concurrency); only capped groups are recorded
- Admin reset (`reset_index_state`, `collection_exists`, `COLLECTION_NAME`) intentionally lives in `backend/reset.py`, NOT here — it reaches into Qdrant + the memory domain (core must not depend on domains)

## Work Guidance
- New shared primitives (config, LLM clients, etc.) belong here; keep `core/` free of FastAPI request/response types and of any domain import
- Do not re-export in `core/__init__.py` — import submodules directly

## Verification
- Import check: `venv/bin/python -c "import core.db, core.models, core.url, core.usage, core.prompts, core.repositories.*"`
- Usage-cap smoke: `PYTHONPATH=. venv/bin/python /tmp/opencode/smoke_usage.py`
- Full app import: `venv/bin/python -c "import backend.main"`

## Child DOX Index

| Path | Purpose |
|---|---|
| `repositories/` | Data-access helpers (users, indexed_repo, conversations, graph) split from the old `backend/state.py` |
