# PRODUCTION.md — Managed infra & high availability

Deploying the app against managed or high-availability infrastructure. The app's
state lives entirely in Postgres (durable state) + Qdrant (vectors) + Redis
(chat-memory queue + ingest lock), so the backend and the ARQ worker are
stateless and can run anywhere. Pair with `SCALE.md` for worker/cache/pool math
and `START_STOP.md` for the dev command sequence.

## Two deployment options

**Option A — self-hosted infra (Docker).** `compose.prod.yml` runs the same
Qdrant/Postgres/Redis with healthchecks, restart policies, and resource hints:

```bash
docker compose -f compose.prod.yml up -d
docker compose -f compose.prod.yml ps
```

**Option B — managed services.** No compose needed — point the env vars at the
managed endpoints and run the backend + ARQ worker as your own services:

| Service | Managed example | Env wiring |
|---|---|---|
| Postgres | RDS / Cloud SQL / Supabase | `DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/db` |
| Qdrant | Qdrant Cloud / self-hosted HA | `QDRANT_MODE=cloud`, `QDRANT_URL=https://…`, `QDRANT_API_KEY=…` |
| Redis | ElastiCache / Upstash / Redis Cloud | `REDIS_URL=redis://…` |

The backend reads these from `.env` at startup (`load_dotenv`), same as local
dev. `QDRANT_MODE` defaults to `server`; set it to `cloud` for managed Qdrant
(see `vector_store/qdrant_client.py`).

## High-availability notes

- **Backend**: run ≥2 processes (`uvicorn --workers N`) across ≥2 hosts behind a
  load balancer. All coordination state is shared: Postgres/Qdrant/Redis are
  external, the ingest lock + global gate are Redis-backed (cross-host
  dedupe), and per-worker in-memory caches are just that — per worker. A
  worker can be torn down at any time (background pipeline threads die with
  it; their ingest lock/gate slots expire via TTL).
- **ARQ worker**: stateless; run as many as you need against the same Redis.
  Redis down degrades chat to no-memory (never breaks chat) and briefly loses
  the ingest lock's cross-host guarantee (falls back to per-process).
- **Postgres**: enable automated backups / point-in-time recovery. Plan
  `max_connections` ≥ `N_backend_workers × (DB_POOL_SIZE + DB_MAX_OVERFLOW)`
  plus a few for the ARQ worker — e.g. 2 backend workers × (5 + 10) + 5 ≈ 35.
- **Qdrant**: enable snapshots for the two collections (`code_chunks`,
  `long_term_memory`). Changing an embedding model's dimensions requires
  wiping + re-embedding everything (see `vector_store/AGENTS.md`).
- **Redis**: `compose.prod.yml` runs with AOF persistence. A Redis restart
  drops queued memory jobs (they're re-enqueued on the next chat) and briefly
  clears ingest locks (slots are re-acquired). Not data-of-record.

## Health checks

- Liveness: `GET /api/health` — returns `{"status":"ok"}` (no dependencies).
- Readiness: `GET /api/ready` — 200 only when Postgres, Qdrant, and Redis are
  all reachable; 503 with a per-dependency `checks` map otherwise. Point your
  orchestrator/load balancer at it.

## Environment (production delta)

| Env | Prod guidance |
|---|---|
| `DATABASE_URL` | managed Postgres (TLS via `sslmode=require` if supported) |
| `QDRANT_MODE` / `QDRANT_URL` / `QDRANT_API_KEY` | `cloud` + managed endpoint |
| `REDIS_URL` | managed Redis |
| `GITHUB_TOKEN` / `OPENROUTER_API_KEY` / `DEEPSEEK_API_KEY` / Clerk keys | as in dev |
| `WEB_CONCURRENCY` | uvicorn `--workers` count |
| `INGEST_MAX_CONCURRENT` | global pipeline cap (default 2) |
| `CORS_ORIGINS` | the real frontend origin(s), comma-separated |
| `THREADPOOL_SIZE` | per-worker chat concurrency ceiling (default 40) |

## Caveats

- `/api/reset` is auth-gated but has no admin/role check — any signed-in user
  can wipe index data. Add a role check if that matters in your deployment.
