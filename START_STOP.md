# How to Start and Stop the App (Manually)

Run every command from the project root (the folder this file is in), unless it says otherwise. Open a **separate terminal window** for each step that says "(own terminal)".

The stack has 4 pieces:

1. **Infra** — databases, run in Docker (Qdrant, Postgres, Redis)
2. **Backend** — the API server (FastAPI/uvicorn)
3. **Worker** — background jobs for chat memory (arq)
4. **Frontend** — the web UI (React/Vite)

---

## STARTING

### Step 1 — Start the databases (Docker)

```bash
docker compose up -d
```

This starts all 3 at once. To start only one:

```bash
docker compose up -d qdrant
docker compose up -d postgres
docker compose up -d redis
```

Check they are up:

```bash
docker compose ps
```

Optional health checks:

```bash
docker compose exec redis redis-cli ping        # expect: PONG
curl http://localhost:6333/collections          # expect: a JSON line
docker compose exec postgres psql -U librarian -c 'select 1;'
```

For **production/self-hosted** infra (healthchecks, restart policies, resource
hints) use `compose.prod.yml` instead — or managed services (see
`PRODUCTION.md`):

```bash
docker compose -f compose.prod.yml up -d
```

### Step 2 — Start the backend API server (own terminal)

```bash
venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload \
  --reload-exclude 'data/*' --reload-exclude 'frontend/dist/*'
```

- `--reload` means it restarts itself whenever you change code.
- It creates the database tables automatically on startup.

**Production (multi-worker)**: drop `--reload` and pass `--workers`:

```bash
venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers "${WEB_CONCURRENCY:-2}"
```

Multi-worker caveats (per-worker caches, Redis required for the ingest lock,
Postgres connection math) are in `SCALE.md`.

### Step 3 — Start the chat-memory worker (own terminal)

```bash
venv/bin/arq memory.worker.WorkerSettings
```

- Needs Redis from Step 1.
- If this worker is not running, chat still works but has no memory.

### Step 4 — Start the frontend (own terminal)

```bash
cd frontend && npm run dev
```

- Serves the UI (usually http://localhost:5173).
- `/api` requests are forwarded to the backend on :8000 automatically.

After these 4 steps you can use the app in your browser.

---

## GUI / DATABASE TOOLS (optional)

### Qdrant dashboard — browse vectors & chunks

- URL: http://localhost:6333/dashboard
- Available whenever the Qdrant container is up (Step 1).
- Lets you inspect the `code_chunks` and `long_term_memory` collections, points, and vectors.

### Adminer — Postgres GUI (opt-in)

- URL: http://localhost:8080
- Adminer does **not** start with the normal `docker compose up -d` — it is in the optional `tools` profile.
- Start it:

  ```bash
  docker compose --profile tools up -d
  ```

- Stop it:

  ```bash
  docker compose stop adminer
  ```

- Reset it (fresh container):

  ```bash
  docker rm -f librarian-adminer
  ```

- Login details:
  - System: `PostgreSQL`
  - Server: `postgres`
  - User: `librarian`
  - Password: `librarian`
  - Database: `librarian`

---

## TESTS (smoke / integration scripts)

All tests are standalone Python scripts run manually from the repo root (no pytest). `test_09`–`test_11` need nothing; the rest need infra (Step 1) and the relevant API keys in `.env`.

```bash
venv/bin/python tests/test_01_ingestion.py          # clone + scan a repo (needs network)
venv/bin/python tests/test_02_chunking.py           # chunk files into CodeChunks (needs network)
venv/bin/python tests/test_03_embedding.py          # full pipeline: ingest -> chunk -> embed
venv/bin/python tests/test_04_view_embedding.py     # inspect stored embeddings in Qdrant
venv/bin/python tests/test_05_retrieval.py          # hybrid retrieval with scoring
venv/bin/python tests/test_06_wipe_qdrant_db.py     # DELETE + recreate the Qdrant DB — do NOT run casually
venv/bin/python tests/test_07_answer_generation.py  # retrieval + answer generation
venv/bin/python tests/test_08_summarization.py      # per-file LLM summarization
venv/bin/python tests/test_09_memory.py             # chat memory (fake embedder — no API)
venv/bin/python tests/test_10_symbol_graph.py       # symbol-graph regression (no API/infra)
venv/bin/python tests/test_11_evaluation.py         # eval-harness unit smoke (no API/infra)
```

- Tests run best in numeric order (each stage builds on the previous).
- 01–08 spend real API calls (embeddings, LLM); 09–11 are offline.
- `test_06_wipe_qdrant_db.py` wipes **all** chunks — never run it unless you want a clean slate.

---

## EVALUATION (RAG pipeline benchmark)

URL-driven evaluation harness: ingests a repo twice (naive + AST chunks) into isolated Qdrant collections, builds a synthetic golden set from AST entities, runs the 4 pipeline setups (S1 naive vector → S2 AST vector → S3 hybrid RRF → S4 hybrid + rerank), scores 6 metrics, and writes an academic-style **HTML report with figures** plus JSON/Markdown.

Requirements: infra up (Step 1) and in `.env` — `OPENROUTER_API_KEY` (embeddings + reranking) and `DEEPSEEK_API_KEY` (golden-set generation, answers, judging).

```bash
venv/bin/python -m evaluation.runner --repo https://github.com/Saini-cmd/lynko
```

- Output: `data/eval_reports/<repo>_<timestamp>/` → open `report.html` in a browser; `report.md`, `report.json`, and the figure PNGs sit alongside.
- Multiple repos also produce an **aggregate** report comparing them:

```bash
venv/bin/python -m evaluation.runner --repo https://github.com/Saini-cmd/lynko --repo https://github.com/psf/requests
```

Useful flags:

| Flag | What it does |
|---|---|
| `--k N` | Retrieval depth K (default 8) |
| `--n N` | Number of golden questions (default 20) |
| `--out DIR` | Output directory (default `data/eval_reports`) |
| `--regenerate-golden` | Rebuild the cached golden set instead of reusing it |
| `--no-embed` | Skip embedding (only when the repo was already ingested) |
| `--skip-generation` | Skip S4 answer generation + judges (retrieval metrics only, cheaper) |
| `--seed N` | Golden-set sampling seed (default 42) |
| `--verbose` | Show INFO logs |

Notes:

- Golden sets are cached in `evaluation/datasets/<repo>_golden.json` and reused on re-runs (rebuild with `--regenerate-golden`).
- Eval uses its own collections `code_chunks_eval_naive` / `code_chunks_eval_ast` — production `code_chunks` is never touched.
- The first run of a repo is the expensive one (embedding + ~20 questions); re-runs skip already-ingested commits.
- Costs roughly: 20 × (4 retrievals + 1 rerank + 1 answer + 2 judge calls) + 20 one-time golden-set paraphrase calls.

Context-curation ablation (compares how much context to feed the LLM):

```bash
venv/bin/python -m evaluation.context_ablation --golden evaluation/datasets/lynko_golden.json
```

Prints Faithfulness / Answer Relevance / Citation Accuracy / avg tokens / relevant-chunk survival across 4 context policies.

---

## STOPPING

Stop in the **reverse order** — frontend first, databases last.

### Step 1 — Stop the frontend

Go to its terminal and press **Ctrl+C**.

### Step 2 — Stop the chat-memory worker

Go to its terminal and press **Ctrl+C**.

### Step 3 — Stop the backend

Go to its terminal and press **Ctrl+C**.

### Step 4 — Stop the databases

```bash
docker compose stop          # stops containers, keeps all data
# or, to also DELETE all data (fresh start):
docker compose down -v
```

Need to stop only one database?

```bash
docker compose stop redis
```

---

## STARTING AGAIN

Just repeat the STARTING steps. Databases keep their data unless you used `docker compose down -v`.

If the `docker` command says permission denied, put `sg docker -c` in front, e.g.:

```bash
sg docker -c "docker compose up -d"
```
