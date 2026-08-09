# memory/

## Purpose
Hybrid chat memory: **short-term** = the current conversation's recent turns (assembled from PostgreSQL `messages`, with a rolling `conversation_summaries` fallback); **long-term** = cross-conversation raw exchanges vectorized into the Qdrant `long_term_memory` collection and retrieved semantically per user + repo. Heavy vectorization/summarization runs in background ARQ workers, never in the chat request path.

## Ownership
- `store.py` — `MemoryStore`: Qdrant `long_term_memory` store — `ensure_collection` (dense `text_dense` 768-dim Cosine), `upsert_exchange` (idempotent deterministic uuid5 point id), `search` (by `clerk_id` + optional `repo_hash`, excluding the current conversation), `delete_by_conversation`; cached `get_memory_store()` for the request path
- `short_term.py` — `build_history`: last-N raw turns (oldest→newest) with the rolling-summary fallback when the raw history exceeds the token budget; `HistoryContext`; **`build_memory_context`**: read-path assembly = short-term history + long-term memory raw texts (zero-LLM, best-effort — any failure degrades to no memory)
- `worker.py` — ARQ `WorkerSettings` (`vectorize_exchange`, `rollup_session_summary`) + `enqueue_memory_jobs` (sync fire-and-forget enqueue used by the chat endpoints; never raises); run with `venv/bin/arq memory.worker.WorkerSettings`

## Local Contracts
- Long-term memory is scoped per **user + repo**: payload carries `clerk_id`, **`repo_url`** (the scope), `repo_hash` (informational metadata — which commit the exchange was written against), `conversation_id`; retrieval filters `must=[clerk_id, repo_url]` and `must_not=[conversation_id == current]` (complements, not duplicates, short-term history). `repo_url=None` searches the user's memory across repos
- **Scoping is by `repo_url`, not `repo_hash`** — `repo_url` is stable across commits, so long-term memory **survives a sync**: after a conversation re-points to a new commit hash, its memory stays retrievable and keeps accumulating (stale-content risk is covered by `MEMORY_GUIDANCE` in the prompt). Old-commit memory is never orphaned/cleaned by tombstoning
- Exchange text format: `"User: {query} | Assistant: {response}"`; `memory_type` = `raw_exchange` only (MVP — no LLM fact extraction)
- Point id = `uuid5(namespace, f"{conversation_id}-{user_message_id}")` — deterministic → idempotent upserts; string point ids must be valid UUIDs (Qdrant requirement)
- Embeddings reuse `embedding.APIEmbedder` (`BAAI/bge-base-en-v1.5`, 768-dim); `MemoryStore(embedder=...)` is injectable for tests
- Read path is **zero-LLM**: history + raw memory chunks go straight into the prompt (`memory/short_term.py` feeds the Phase-2 prompt builder)
- Rolling summary (`conversation_summaries` table) is maintained by the background summarizer; `last_message_id` is the resume watermark
- **Write path (Phase 3 done)**: `vectorize_exchange` embeds each exchange (idempotent); `rollup_session_summary` summarizes only when ≥ `SUMMARIZE_EVERY` (10, `MEMORY_SUMMARIZE_EVERY`) new messages have accumulated since the watermark, merging into the existing summary via the shared OpenRouter model (`SUMMARIZE_*` config, `summarization/llm_config.py`); watermark advances to the newest summarized message; input capped at `_SUMMARIZE_INPUT_TOKEN_BUDGET` (8k) keeping the most recent messages
- **Cleanup (Phase 4 done)**: `backend.routers.conversations.delete_conversation` purges the conversation's memory points via `get_memory_store().delete_by_conversation` (best-effort, Qdrant-down safe; `conversation_summaries` row cascades on conversation delete); `backend.state.reset_index_state(wipe=True)` deletes the `long_term_memory` collection alongside `code_chunks` (keeps users/history)
- Tunables (`.env`, see `.env.example`): `MEMORY_HISTORY_TURNS`, `MEMORY_HISTORY_TOKENS`, `MEMORY_TOP_K`, `MEMORY_SUMMARIZE_EVERY`, `MEMORY_SUMMARIZE_DEFER_SECONDS` (read by `short_term.py` / `worker.py`)
- Requires Qdrant + Redis up (`docker compose up -d qdrant redis`); ARQ worker runs with `venv/bin/arq memory.worker.WorkerSettings` — Redis down degrades to no-memory, never breaks chat
- Conversation deletion must purge that conversation's memory points (`MemoryStore.delete_by_conversation`); reset wipes the whole collection (keeps users/history) — both wired in Phase 4

## Work Guidance
- Changing the embedding model requires matching `EMBEDDING_DIM` here to the embedder's dimension
- Memory deletions should follow the repo's cleanup semantics (conversation-scoped, never user-wide in a single call)

## Verification
- Phase-1 smoke: `python /tmp/opencode/smoke_memory_phase1.py` (fake embedder — no API calls)
- Phase-2 read path: `python /tmp/opencode/verify_phase2.py` (stubbed embedder)
- Phase-3 worker logic: `python /tmp/opencode/verify_phase3_offline.py` (fake summarizer); live round-trip: run `venv/bin/arq memory.worker.WorkerSettings`, then `python /tmp/opencode/verify_phase3_live.py` (real embed + one ling-3.0-flash call)
- Regression: `python tests/test_09_memory.py` (fake embedder — store round-trip + short-term assembly)

## Child DOX Index
*None*
