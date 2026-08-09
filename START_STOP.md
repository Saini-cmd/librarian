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

### Step 2 — Start the backend API server (own terminal)

```bash
venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload \
  --reload-exclude 'data/*' --reload-exclude 'frontend/dist/*'
```

- `--reload` means it restarts itself whenever you change code.
- It creates the database tables automatically on startup.

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
