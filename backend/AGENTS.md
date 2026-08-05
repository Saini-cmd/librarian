# backend/

## Purpose
FastAPI server providing REST API endpoints for repo ingestion and chat.

## Ownership
- `main.py` — FastAPI application with CORS, routes, in-memory APP_STATE, cached pipeline singletons
- `auth.py` — Clerk JWT verification (RS256, JWKS), `get_current_user` dependency, webhook verification
- `state.py` — State management helpers (markers, index state, Q&A markdown, reset)
- `routers/` — **Planned**: auth_webhook, users, conversations, repositories router modules
- `database.py` — **Planned**: async SQLAlchemy engine + session factory + get_db dependency
- `models.py` — **Planned**: User, Conversation, Message, UserRepo ORM models
- Delegates pipeline orchestration to `orchestration/` and RAG to `rag/`

## Local Contracts
- All API paths prefixed with `/api` (proxied by Vite dev server)
- Clerk JWT optional on some endpoints (`get_current_user` dependency); 401 on invalid/missing for protected routes
- JWKS fetched once from Clerk issuer and cached via `@lru_cache`
- Endpoints:
  - `GET /api/health` — health check (no auth)
  - `GET /api/status` — pipeline state, Qdrant collection status (no auth)
  - `POST /api/reset` — wipe Qdrant + data files (no auth — should be protected)
  - `POST /api/process` — ingest repo (auth required)
  - `POST /api/chat` — query → retrieve → generate (auth required)
  - `POST /api/chat/stream` — SSE streaming chat (auth required)
- Uses `uvicorn` as ASGI server with hot-reload in dev
- In-memory `APP_STATE` dict for pipeline progress (lost on restart)
- Marker files in `data/chunks/` for persisted repo/state tracking

## Work Guidance
- Adding a new router: create file in `routers/`, mount in `main.py`
- Auth is per-route via `Depends(get_current_user)` — not middleware-based
- Clerk webhook receiver (`POST /api/webhooks/clerk`) requires `CLERK_WEBHOOK_SECRET` env var
- Planned: switch from `APP_STATE` + flat files to Supabase PostgreSQL via SQLAlchemy async

## Verification
- Start with `uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload`

## Child DOX Index
*None*
