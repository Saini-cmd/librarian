# SCALE.md — Concurrency & scaling notes

How the app scales horizontally, what is per-process vs shared, and the knobs
that matter under concurrent multi-user load. Pair with `START_STOP.md` for the
exact command sequence and `backend/AGENTS.md` for endpoint contracts.

## Architecture recap

- **FastAPI (uvicorn)** — REST + SSE. Sync `def` endpoints run in FastAPI's
  thread pool; long-running `/api/process` and `/sync` do their heavy work in a
  background `threading.Thread` and stream progress via SSE.
- **PostgreSQL** — durable state (users, conversations, messages, indexed
  repos, graphs, summaries, citations).
- **Qdrant** — vectors (`code_chunks`) + chat long-term memory
  (`long_term_memory`).
- **Redis** — chat-memory job queue (ARQ worker) + the **ingest lock**.
- **ARQ worker** — separate process running chat-memory background jobs.

## Scaling the backend: uvicorn `--workers N`

Single-process dev command: `uvicorn backend.main:app --port 8000` (dev uses
`--reload`, which is incompatible with `--workers`).

Production multi-worker:

```bash
venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-2}
```

Each worker is a separate OS process. **What is per-worker vs shared:**

| State | Per worker? | Implication |
|---|---|---|
| `RetrievalPipeline` / `AnswerGenerator` / `get_memory_store` `lru_cache` singletons | yes | Multiply memory ×N workers |
| BM25 index cache (bounded LRU, `BM25_CACHE_SIZE`) | yes | ×N memory, but bounded per worker |
| Graph rebuild locks, `_PARSERS`, ingest-lock in-process fallback | yes | Correct within a worker only |
| Ingest lock (Redis primary) | no — Redis is shared | Dedupes concurrent ingests **across** workers |
| PostgreSQL / Qdrant pools | yes | Connection count = N × (pool size + overflow) |
| ARQ worker queue | no — Redis | Scale by running more ARQ workers |

### Non-negotiables in multi-worker mode

- **Redis must be up.** The ingest lock's primary is Redis `SET NX EX`; its
  in-process fallback only dedupes within a single process. With `--workers N`
  and Redis down, two workers could ingest the same commit concurrently
  (duplicate work — Phase 1/2 DB + clone safety keep it from corrupting data).
- **`--reload` off.** uvicorn refuses `--reload` with `--workers`.

### PostgreSQL connection math

Every worker opens its own SQLAlchemy pool:
`DB_POOL_SIZE + DB_MAX_OVERFLOW` connections (default 5 + 10 = 15). With N
workers, `N × 15` connections against Postgres's `max_connections` (default
100). For 2 workers that's 30 — comfortable; for more workers, either raise
`max_connections` or lower `DB_POOL_SIZE`/`DB_MAX_OVERFLOW`. Pipelines no
longer pin a connection for their whole run (session is opened only for the
finalize step), so steady-state usage is short-lived.

### Chat concurrency within a worker

Chat endpoints are sync `def` → they occupy FastAPI's thread pool (default 40,
env-tunable via `THREADPOOL_SIZE`, applied in the app lifespan). Retrieval +
LLM generation are blocking; a burst of concurrent chats can saturate the pool.
Raise `THREADPOOL_SIZE` or add workers (`--workers`) — the two levers.

### Health probes

`/api/health` is the no-dependency liveness probe; `/api/ready` returns 200
only when Postgres, Qdrant, and Redis are all reachable (503 with a per-dep
`checks` map otherwise) — point load balancers/orchestrators at `/api/ready`.

## Concurrency knobs (env)

| Env | Default | Purpose |
|---|---|---|
| `INGEST_LOCK_TTL_SECONDS` | 900 | Ingest-lock TTL (heartbeat-renewed while a pipeline runs) |
| `INGEST_WAIT_MAX_SECONDS` | 1800 | How long a second caller waits on a busy commit before giving up |
| `INGEST_WAIT_POLL_SECONDS` | 2 | Wait-and-reuse poll interval |
| `INGEST_MAX_CONCURRENT` | 2 | Global cap on concurrent pipelines across all users/commits (0 = unlimited) |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | 5 / 10 | Per-worker Postgres pool |
| `BM25_CACHE_SIZE` | 16 | Per-worker BM25 index LRU cap |
| `THREADPOOL_SIZE` | 40 | FastAPI sync-endpoint thread pool per worker |
| `CORS_ORIGINS` | Vite dev origins | Comma-separated allowed origins (set to your prod frontend) |

## Ingest concurrency cap

Per-commit dedupe (the ingest lock) stops duplicate work on the **same**
commit, but distinct commits could still fan out without bound — each pipeline
spawns 5 embed + 5 summarize workers against OpenRouter/DeepSeek.
`GlobalIngestGate` caps this globally (`INGEST_MAX_CONCURRENT`, default 2): a
caller that can't get a slot streams the same `waiting` state until one frees
(up to `INGEST_WAIT_MAX_SECONDS`). The gate counter slides its TTL on acquire
and is renewed by the pipeline heartbeat, so a crashed pipeline's slot expires
instead of leaking. Redis down → per-process `BoundedSemaphore` fallback.

## Background workers (ARQ)

`venv/bin/arq memory.worker.WorkerSettings` runs `max_jobs=4` concurrent jobs
per process. Run multiple ARQ processes to scale chat-memory work; Redis is the
queue so workers can run on different hosts. Redis down degrades chat to
no-memory (never breaks chat).

## Managed infra / HA

Self-hosted infra with healthchecks/resource hints: `compose.prod.yml`. Managed
services (Postgres RDS/Cloud SQL, Qdrant Cloud, Redis ElastiCache/Upstash):
point `DATABASE_URL` / `QDRANT_URL` / `REDIS_URL` at them and run the backend +
ARQ worker as your own services — full details, HA/backup guidance, and
`max_connections` planning in `PRODUCTION.md`.
