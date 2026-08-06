# DOX framework

- DOX is highly performant AGENTS.md hierarchy installed here
- Agent must follow DOX instructions across any edits

## Core Contract

- AGENTS.md files are binding work contracts for their subtrees
- Work products, source materials, instructions, records, assets, and durable docs must stay understandable from the nearest applicable AGENTS.md plus every parent AGENTS.md above it

## Read Before Editing

1. Read the root AGENTS.md
2. Identify every file or folder you expect to touch
3. Walk from the repository root to each target path
4. Read every AGENTS.md found along each route
5. If a parent AGENTS.md lists a child AGENTS.md whose scope contains the path, read that child and continue from there
6. Use the nearest AGENTS.md as the local contract and parent docs for repo-wide rules
7. If docs conflict, the closer doc controls local work details, but no child doc may weaken DOX

Do not rely on memory. Re-read the applicable DOX chain in the current session before editing.

## Update After Editing

Every meaningful change requires a DOX pass before the task is done.

Update the closest owning AGENTS.md when a change affects:

- purpose, scope, ownership, or responsibilities
- durable structure, contracts, workflows, or operating rules
- required inputs, outputs, permissions, constraints, side effects, or artifacts
- user preferences about behavior, communication, process, organization, or quality
- AGENTS.md creation, deletion, move, rename, or index contents

Update parent docs when parent-level structure, ownership, workflow, or child index changes. Update child docs when parent changes alter local rules. Remove stale or contradictory text immediately. Small edits that do not change behavior or contracts may leave docs unchanged, but the DOX pass still must happen.

## Hierarchy

- Root AGENTS.md is the DOX rail: project-wide instructions, global preferences, durable workflow rules, and the top-level Child DOX Index
- Child AGENTS.md files own domain-specific instructions and their own Child DOX Index
- Each parent explains what its direct children cover and what stays owned by the parent
- The closer a doc is to the work, the more specific and practical it must be

## Child Doc Shape

- Create a child AGENTS.md when a folder becomes a durable boundary with its own purpose, rules, responsibilities, workflow, materials, or quality standards
- Work Guidance must reflect the current standards of the project or user instructions; if there are no specific standards or instructions yet, leave it empty
- Verification must reflect an existing check; if no verification framework exists yet, leave it empty and update it when one exists

Default section order:
- Purpose
- Ownership
- Local Contracts
- Work Guidance
- Verification
- Child DOX Index

## Style

- Keep docs concise, current, and operational
- Document stable contracts, not diary entries
- Put broad rules in parent docs and concrete details in child docs
- Prefer direct bullets with explicit names
- Do not duplicate rules across many files unless each scope needs a local version
- Delete stale notes instead of explaining history
- Trim obvious statements, repeated rules, misplaced detail, and warnings for risks that no longer exist

## Closeout

1. Re-check changed paths against the DOX chain
2. Update nearest owning docs and any affected parents or children
3. Refresh every affected Child DOX Index
4. Remove stale or contradictory text
5. Run existing verification when relevant
6. Report any docs intentionally left unchanged and why

## User Preferences

When the user requests a durable behavior change, record it here or in the relevant child AGENTS.md

- Always verify and keep DOX up to date with the project before and after any meaningful change
- Use relevant installed skills (in `~/.agents/skills/`) whenever a task matches their domain
- Conserve tokens: do NOT run `npm run build` or test suites repeatedly for verification unless explicitly asked. Prefer targeted checks (syntax parse, single-file introspection, focused smoke) and run full builds/tests only when the user requests them.

## Start / Stop Runbook

All commands run from the repository root. The app has three layers: infra (Docker), backend (uvicorn), frontend (Vite).

### 1. Infra — Qdrant + PostgreSQL (Docker)

```bash
docker compose up -d     # start qdrant (6333) + postgres (5432) in background
docker compose ps        # check status
docker compose down      # stop containers (data volumes preserved)
docker compose down -v   # stop AND wipe all data (Postgres + Qdrant volumes)
```

- Containers auto-start on boot (`restart: unless-stopped`)
- If `docker` gives permission denied, run `sg docker -c "<command>"` or re-login after the group change

### 2. Backend — FastAPI

```bash
venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload   # dev (hot reload)
venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000             # prod-style
```

- Requires infra up (Postgres + Qdrant) — tables auto-create on startup
- Stop with `Ctrl+C` (or `kill <pid>`)

### 3. Frontend — React/Vite

```bash
cd frontend && npm run dev     # dev server on :5173, proxies /api to :8000
cd frontend && npm run build   # production build to frontend/dist
```

- Stop with `Ctrl+C`

### 4. GUI tools (browsers)

```bash
open http://localhost:6333/dashboard   # Qdrant web dashboard — browse code_chunks, points, vectors (always available when infra up)
open http://localhost:8080             # Adminer — Postgres GUI (opt-in, tools profile)
```

- Adminer start/stop (opt-in service, does NOT run with normal `docker compose up -d`):
  - Start: `docker compose --profile tools up -d`
  - Stop: `docker compose stop adminer`
- Adminer login: system `PostgreSQL`, server `postgres`, user `librarian`, password `librarian`, db `librarian`

### All-in-one (dev)

```bash
./dev.sh                       # starts infra (Docker) + backend + frontend; Ctrl+C stops everything cleanly
KEEP_INFRA=1 ./dev.sh          # same, but leaves Docker containers running on exit
```

- `dev.sh` waits for Qdrant + Postgres to be healthy before starting the backend, keeps hot reload (uvicorn `--reload`, Vite HMR), and tears down all processes + runs `docker compose down` on exit
- Auto-falls back to `sg docker -c` if your session lacks the `docker` group

### Reset app data (keep infra running)

```bash
curl -X POST http://localhost:8000/api/reset   # wipes Qdrant collection + index data, keeps users/history
```

## Child DOX Index

### Top-Level Durable Boundaries

| Path | Purpose |
|---|---|
| `backend/` | FastAPI server — REST API for repo ingestion, chat, users, conversations, repos; PostgreSQL-backed state (sync SQLAlchemy) |
| `chunking/` | Semantic code chunking (AST + text) — no pickle, no summaries |
| `embedding/` | Embedding pipeline — vectorize chunks via OpenRouter API and upsert to Qdrant |
| `frontend/` | React 18 SPA — daisyUI 5 + Tailwind CSS 4, brutalist dark theme, router-based pages (Landing, App, Settings), Axios API client with Clerk auth |
| `ingestion/` | Git clone (shallow, depth=1) + file scanning for downstream chunking |
| `orchestration/` | Pipeline orchestrator — clone → chunk → summarize → embed → cleanup |
| `rag/` | Answer generation — context building, prompt construction, LLM (DeepSeek via ChatOpenAI) |
| `reranking/` | Reranking via OpenRouter API (cohere/rerank-4-fast) |
| `summarization/` | Per-file LLM summarization (DeepSeek via ChatOpenAI) stored in PostgreSQL |
| `symbol_graph/` | Symbol graph builder — entity/file nodes + usage edges from Qdrant AST chunks (serves the frontend Graph view) |
| `retrieval/` | Hybrid retrieval — dense vector + BM25 + RRF + rerank |
| `tests/` | Smoke-test scripts for each pipeline stage |
| `vector_store/` | Qdrant client singleton and vector management (local Docker server default; cloud/embedded dormant) |

### Non-Durable (owned by root)

| Path | Reason |
|---|---|
| `data/` | Runtime artifacts (cloned repos — transient, cleaned after ingest); durable data lives in PostgreSQL/Qdrant |
| `qdrant_db/` | Qdrant persistent storage (auto-managed) |
| `venv/` | Python virtual environment (not tracked) |
| `.env` | Environment configuration (secrets, endpoints) |
| `.env.local` | Local override env (Clerk secret key) — not tracked |
| `final-plan.md` | Implementation plan artifact — not durable code |
| `PLAN.md` | Outdated planning doc — kept for reference |
| `ACTIONS.md` | Scratchpad — not tracked |
| `dev.sh` | Dev startup script — convenience only |
| `.agents/` | Agent skills and configurations (installed by `npx skills`) |

### Root-Owned Durable Config

| Path | Purpose |
|---|---|
| `docker-compose.yml` | Local infra — `qdrant` (port 6333) + `postgres` (port 5432) services, named volumes; opt-in `tools` profile adds `adminer` (port 8080) |
| `.env.example` | Documents every required env key (model APIs, local infra, Clerk) |

