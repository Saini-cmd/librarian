# backend/

## Purpose
FastAPI server providing REST API for repo ingestion, chat, users, conversations, and repositories. Durable state is stored in local PostgreSQL (sync SQLAlchemy); vectors live in local Qdrant (Docker). Delegates pipeline orchestration to `orchestration/` and RAG to `rag/`.

## Ownership
- `main.py` — FastAPI app: CORS, lifespan (`init_db`), mounts routers, core endpoints (process, chat, chat/stream, status, reset, health)
- `auth.py` — Clerk JWT verification (RS256, JWKS), `get_current_user` dependency
- `state.py` — DB data-access helpers: pipeline state, users, repos, conversations, QA records, reset
- `database.py` — Sync SQLAlchemy engine (`DATABASE_URL`), `SessionLocal`, `Base`, `get_db`, `init_db` (create_all on startup)
- `models.py` — ORM models: `User`, `Conversation`, `Message`, `UserRepo`, `PipelineState`, `FileSummary`, `QaRecord`
- `routers/users.py` — `GET/PATCH /api/users/me` with lazy Clerk user upsert
- `routers/conversations.py` — Conversation CRUD + nested messages
- `routers/repositories.py` — `GET /api/repositories` (user's indexed repos)

## Local Contracts
- All API paths prefixed with `/api` (proxied by Vite dev server)
- Clerk JWT required on protected routes (`Depends(get_current_user)`); 401 on invalid/missing
- DB: sync SQLAlchemy + psycopg2; tables auto-created at startup via `create_all` (Alembic deferred)
- Pipeline state persisted in single-row `pipeline_state` table (replaces old in-memory `APP_STATE` + marker/index files)
- Chat persists `Message` rows; conversation auto-created when `conversation_id` is null (title = first message)
- QA answers stored as `QaRecord` rows (replaces `data/responses/latest.md`)
- `reset` wipes Qdrant collection + `user_repos`, `file_summaries`, `qa_records`, `pipeline_state`; preserves users and conversation history
- `collection_exists` fails safe (returns `False`) when Qdrant is unreachable
- Endpoints:
  - `GET /api/health` — health check (no auth)
  - `GET /api/status` — pipeline state + Qdrant collection status (no auth)
  - `POST /api/reset` — wipe Qdrant + index data (no auth — should be protected)
  - `POST /api/process` — ingest repo (auth required)
  - `POST /api/chat` — query → retrieve → generate, persists messages (auth required)
  - `POST /api/chat/stream` — SSE streaming chat, persists messages (auth required)

## Work Guidance
- Adding a new router: create file in `routers/`, mount in `main.py`
- Auth is per-route via `Depends(get_current_user)` — not middleware-based
- New ORM models: add to `models.py`; tables auto-create on next startup
- `chat/stream` manages its own `SessionLocal` session (outlives the request via the SSE generator)
- Clerk webhook receiver (`POST /api/webhooks/clerk`) not yet implemented — users are lazily upserted on first authenticated request

## Verification
- Start with `uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload` (requires local Postgres + Qdrant up)
- Smoke-test the DB + router layer with `python /tmp/opencode/smoke_test.py`

## Child DOX Index
*None*
