#!/usr/bin/env bash
# dev.sh — full-stack dev launcher.
# Starts Docker infra (Qdrant + PostgreSQL), then backend + frontend with hot reload.
# On exit (Ctrl+C, crash, or kill) stops everything cleanly.
# Set KEEP_INFRA=1 to leave the Docker containers running on exit.
set -euo pipefail
set -m  # job control: background jobs get their own process groups for clean shutdown

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT_DIR}"

PROCS=()
CLEANED=0
TEARDOWN_INFRA=1
[[ "${KEEP_INFRA:-0}" == "1" ]] && TEARDOWN_INFRA=0
dk() { "$@"; }  # default docker runner; may be overridden below

# per-process log prefixes so backend/frontend output is distinguishable
if [[ -t 1 ]]; then
  B_PREFIX=$'\e[36m[backend]\e[0m '
  F_PREFIX=$'\e[35m[frontend]\e[0m '
else
  B_PREFIX='[backend] '
  F_PREFIX='[frontend] '
fi

fail() { echo "dev.sh: error: $*" >&2; exit 1; }

cleanup() {
  set +e
  if [[ "${CLEANED}" == "1" ]]; then return; fi
  CLEANED=1
  echo ""
  echo "dev.sh: shutting down..."
  for pid in "${PROCS[@]}"; do
    kill -TERM -"${pid}" 2>/dev/null || kill -TERM "${pid}" 2>/dev/null
  done
  for pid in "${PROCS[@]}"; do
    wait "${pid}" 2>/dev/null
  done
  if [[ "${TEARDOWN_INFRA}" == "1" ]]; then
    echo "dev.sh: stopping infra (docker compose down)..."
    dk docker compose down 2>/dev/null || true
  else
    echo "dev.sh: keeping infra running (KEEP_INFRA=1)"
  fi
  echo "dev.sh: done."
  exit 0  # end immediately — prevents resuming the script after a signal trap
}
trap cleanup EXIT INT TERM

# --- pre-flight checks ---

command -v docker >/dev/null 2>&1 || fail "docker not found. Install Docker first."
if docker info >/dev/null 2>&1; then
  dk() { "$@"; }
elif sg docker -c "docker info" >/dev/null 2>&1; then
  echo "dev.sh: docker needs the 'docker' group — using 'sg docker' for all commands."
  dk() { sg docker -c "$*"; }
else
  fail "cannot talk to docker daemon. If you just joined the 'docker' group, log out/in, or run: sg docker -c './dev.sh'"
fi
test -d "${ROOT_DIR}/venv" || fail "venv/ missing — run: python3 -m venv venv && venv/bin/pip install -r requirements.txt"
test -d "${ROOT_DIR}/frontend/node_modules" || fail "frontend/node_modules missing — run: cd frontend && npm install"

# --- 1. infra (Docker) ---

echo "dev.sh: starting infra (qdrant + postgres)..."
dk docker compose up -d

echo "dev.sh: waiting for qdrant on :6333 ..."
for i in $(seq 1 30); do
  curl -sf --max-time 2 http://localhost:6333/collections >/dev/null 2>&1 && break
  [[ "${i}" == "30" ]] && fail "qdrant did not become ready in time"
  sleep 1
done

echo "dev.sh: waiting for postgres on :5432 ..."
for i in $(seq 1 30); do
  venv/bin/python -c "
import psycopg2, sys
try:
    psycopg2.connect(host='localhost', port=5432, user='librarian', password='librarian', dbname='librarian', connect_timeout=2)
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null && break
  [[ "${i}" == "30" ]] && fail "postgres did not become ready in time"
  sleep 1
done

# --- 2. backend (hot reload) ---

echo "dev.sh: starting backend (uvicorn, hot reload) on :8000 ..."
(
  set -o pipefail
  {
    source "${ROOT_DIR}/venv/bin/activate"
    exec venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload \
      --reload-exclude 'data/*' --reload-exclude 'frontend/dist/*'
  } 2>&1 | sed -u "s/^/${B_PREFIX}/"
) &
BACKEND_PID=$!
PROCS+=("${BACKEND_PID}")

# --- 3. frontend (vite, HMR) ---

echo "dev.sh: starting frontend (vite) on :5173 ..."
(
  set -o pipefail
  {
    cd "${ROOT_DIR}/frontend"
    exec npm run dev -- --host 0.0.0.0
  } 2>&1 | sed -u "s/^/${F_PREFIX}/"
) &
FRONTEND_PID=$!
PROCS+=("${FRONTEND_PID}")

echo "dev.sh: stack up — backend :8000, frontend (vite, auto-port), docker infra. Ctrl+C to stop everything."

# brief wait so the backend has a chance to boot before we report status
for i in $(seq 1 20); do
  curl -sf --max-time 2 http://localhost:8000/api/health >/dev/null 2>&1 && break
  sleep 1
done
curl -sf --max-time 2 http://localhost:8000/api/health >/dev/null 2>&1 \
  || echo "dev.sh: warning: backend not healthy yet (will retry via its own reload)."

# --- wait for either process to exit (crash => teardown; Ctrl+C => INT trap) ---
# NOTE: use a liveness poll, not `wait -n` — bash defers signal traps while
# blocked in `wait`, which would hang the stack on Ctrl+C.
while kill -0 "${BACKEND_PID}" 2>/dev/null && kill -0 "${FRONTEND_PID}" 2>/dev/null; do
  sleep 1
done
