# backend/

## Purpose
FastAPI server providing REST API for repo ingestion, chat, users, conversations, and repositories. Durable state is stored in local PostgreSQL (sync SQLAlchemy) across **7 tables** keyed per-commit by `repo_hash`; vectors live in local Qdrant (Docker). Delegates pipeline orchestration to `orchestration/` and RAG to `rag/`. Schema reference: `DB_SCHEMA.md`.

## Ownership
- `main.py` — FastAPI app: CORS, lifespan (`init_db`), mounts routers, core endpoints (process, chat, chat/stream, status, reset, health); persists the ingested repo's symbol graph and the `indexed_repo` row after `/api/process`
- `auth.py` — Clerk JWT verification (RS256, JWKS), `get_current_user` dependency
- `state.py` — DB data-access helpers: users, indexed repos, user-repo derivation, conversations, messages, repo graphs, reset
- `database.py` — Sync SQLAlchemy engine (`DATABASE_URL`), `SessionLocal`, `Base`, `get_db`, `init_db` (create_all on startup)
- `models.py` — ORM models (7 tables): `User`, `IndexedRepo`, `FileSummary`, `RepoGraph`, `Conversation`, `Message`, `Citation`
- `routers/users.py` — `GET/PATCH /api/users/me` with lazy Clerk user upsert (`name` field)
- `routers/conversations.py` — Conversation CRUD + nested messages (owned by `clerk_id`, point at a `repo_hash`)
- `routers/repositories.py` — `GET /api/repositories` (user's repos derived from conversations), repo-scoped graph/summary/chunks (keyed by `repo_hash`), `updates` probe, and `sync` (the diff/sync feature)

## Local Contracts
- All API paths prefixed with `/api` (proxied by Vite dev server)
- Clerk JWT required on protected routes (`Depends(get_current_user)`); 401 on invalid/missing
- DB: sync SQLAlchemy + psycopg2; **7 tables**: `users`, `indexed_repo`, `file_summary`, `repo_graph`, `conversations`, `messages`, `citation`. New tables auto-create via `create_all` (Alembic deferred); changes to existing tables need a manual drop/recreate (no migration tooling)
- **Identity = `repo_url` + `repo_hash`**: `repo_url` (canonicalized by `normalize_repo_url`) is the repo-level identity; `repo_hash` (git HEAD SHA) is the globally-unique commit identity. `repo_name` is display-only (derived from the URL), never used for lookups/scoping. Qdrant scoping is **hash-only** (`repo_hash` payload filter) — the `repo`/URL name filter was removed everywhere
- **Per-commit identity**: `indexed_repo.repo_hash` (git HEAD SHA) is the unique key; the same repo at different commits = separate rows. `conversations.repo_hash`, `file_summary.repo_hash`, `repo_graph.repo_hash` all FK to it
- **A user's repos are derived from their conversations** (distinct `repo_url`s, one row per repo = most recently active commit; no user↔repo join table). `user_repo_exists(clerk_id, repo_url)` checks ownership by URL
- **`/api/process` is probe-first + SSE**: `GitHubAPIFetcher.remote_head_sha(url)` (`git ls-remote`) checks the remote HEAD. If that hash already exists in `indexed_repo` (global across all users), the pipeline is skipped and a conversation is opened on that commit. Otherwise the pipeline runs in a **background thread** and progress is streamed over SSE: `{type: progress, stage, progress, message}` events then a final `{type: result, result, done}` or `{type: error, error, done}`. Each long-running endpoint (`/api/process`, `/sync`) creates its own `SessionLocal` (used by the background thread) and streams via a `queue.Queue` with a `: ping` heartbeat. No name-based short-circuit
- **Summaries and graphs are keyed by `repo_hash`** — `file_summary` and `repo_graph` FK to `indexed_repo.repo_hash`. Qdrant chunks carry `repo_url` + `repo_hash` in their payload
- **Durable citations**: each `[C1]` marker is written to the `citation` table (`write_citations`) keyed by `message_id` + `repo_hash` + `chunk_id` — this is what retains a chunk during old-commit cleanup. The UI-facing snapshot stays on `Message.citation` (JSON, no snippet). `cited_chunk_ids(repo_hash)` returns the retained chunk ids
- Chat is repo-aware: `/api/chat` and `/api/chat/stream` accept optional `repo_hash`; `resolve_conversation_repo` returns `(repo_hash, repo_name)` with precedence conversation > requested hash > none; retrieval scopes by `repo_hash` only, summaries load by `repo_hash`
- Assistant `Message` rows carry a `citation` JSON map (one entry per cited chunk). Citations store `repo_hash`, `chunk_id`, `file_path`, lines, `symbol`, `language` — the `citation` table rows are the durable record
- **Messages are stamped with `repo_hash`** (the commit they were sent/answered against, via `add_message(..., repo_hash=...)`). After a sync re-points a conversation to the new commit, pre-sync messages keep their old hash — the frontend renders a sync-boundary divider where consecutive messages differ in `repo_hash`
- `indexed_repo.status` values: `pending` | `indexing` | `indexed` | `syncing` | `failed` | `deleted`. Soft-deleted (`deleted`) commits are hidden from `latest_indexed_repo_by_url` and `list_user_repos`; their non-cited chunks are purged via `VectorIndexer.delete_by_repo_hash` / `delete_points_by_repo_hash` (cited chunks retained)
- **Sync** (`POST /api/repositories/{repo_hash}/sync`): probes the remote HEAD; if changed, re-ingests (or reuses an already-indexed newer commit via global hash lookup), re-points the **caller's** conversations for that repo to the new hash, then tombstones (`status='deleted'`) each old commit with zero remaining conversations (any user), deleting its non-cited chunks + `file_summary` + `repo_graph` rows. Old commits stay live and chat on them keeps working until a sync re-points/tombstones. `GET /api/repositories/{repo_hash}/updates` is the cheap change probe (`updates_available` + `remote_hash`)
- **No `pipeline_state` / `qa_records` tables** — `GET /api/status` derives `phase`/`ready`/`indexed_repo_name` from the caller's repos; the frontend no longer polls it (process + sync stream progress via SSE)
- `reset` detaches conversations from repos (`repo_hash = NULL`), then wipes Qdrant collection + `citation` + `repo_graph` + `indexed_repo` (cascades `file_summary`); keeps `users` and chat history
- Endpoints:
  - `GET /api/health` — health check (no auth)
  - `GET /api/status` — derived repo state + Qdrant collection status (auth optional)
  - `POST /api/reset` — wipe Qdrant + index data (no auth — should be protected)
  - `POST /api/process` — probe remote HEAD; skip-to-chat if the hash is already indexed (global), else ingest; **streams SSE progress** (`progress` → `result`/`error` events), returns `conversation_id` + `repo_hash` in the final result event (auth required)
  - `POST /api/chat` / `/api/chat/stream` — query → retrieve → generate, persists messages (auth required)
  - `GET /api/repositories` — one `RepoOut` per repo (latest active commit), including `repo_hash`
  - `GET /api/repositories/{repo_hash}/graph` — symbol graph for that commit (auth, ownership via `repo_url`; lazy build fallback)
  - `GET /api/repositories/{repo_hash}/summary?file_path=` — stored per-file summary (auth, ownership checked)
  - `GET /api/repositories/{repo_hash}/chunks/{chunk_id}` — full chunk payload from Qdrant (auth; ownership via `repo_url`, payload `repo_hash` must match). **Tombstoned (`deleted`) commits are allowed here** so retained cited chunks stay clickable after a sync; 404 on missing/unowned chunk
  - `GET /api/repositories/{repo_hash}/chunks?file_path=` — all chunks for one file in a commit, sorted by line span (`vector_store.scroll_chunks_by_file`; chunks tile the file, the frontend reassembles full source from them for the graph panel's "complete code" view). Ownership checked; tombstoned commits rejected (live graph only)
  - `POST /api/repositories/{repo_hash}/explain` — **stateless** SSE explanation of a code node (graph panel Explain button): client sends node metadata + code, `LLMClient` streams `token` events then `done` (or `event: error`); nothing persisted, no conversation/message rows; capped at `LLMConfig(max_tokens=700)` (~500 words) with a "under 500 words" instruction in the system prompt
  - `GET /api/repositories/{repo_hash}/updates` — `{repo_hash, updates_available, remote_hash}` via `git ls-remote` (auth, ownership checked)
  - `POST /api/repositories/{repo_hash}/sync` — sync-to-latest commit; **streams SSE progress**, final result `{status, repo_hash, files_discovered, chunks_created, tombstoned}` or `{status: up_to_date}` (auth, ownership checked)
- **Design principle: minimize re-ingestion** — re-ingesting is cost-heavy (clone + chunk + summarize + embed via OpenRouter). The global hash probe short-circuits known commits across users; sync reuses already-indexed commits; lazy rebuilds (graph, summaries) are preferred over pipeline re-runs

## Work Guidance
- Adding a new router: create file in `routers/`, mount in `main.py`
- Auth is per-route via `Depends(get_current_user)` — not middleware-based
- New ORM models/tables: add to `models.py`; new tables auto-create on next startup, but changes to existing tables need a manual `ALTER TABLE` or drop/recreate (no migration tooling)
- `chat/stream` manages its own `SessionLocal` session (outlives the request via the SSE generator)
- Clerk webhook receiver (`POST /api/webhooks/clerk`) not yet implemented — users are lazily upserted on first authenticated request

## Verification
- Start with `uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload --reload-exclude 'data/*' --reload-exclude 'frontend/dist/*'` (requires local Postgres + Qdrant up) — the `data/*` exclude keeps cloned repos (`data/repos/`) from triggering a mid-pipeline reload
- Smoke-test the DB + router layer with `python /tmp/opencode/smoke_schema.py` (set `PYTHONPATH` to the repo root)

## Child DOX Index
*None*
