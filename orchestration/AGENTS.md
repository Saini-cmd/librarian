# orchestration/

## Purpose
Orchestrates the full ingestion pipeline: clone → scan → **file-size gate** → chunk → **chunk-size gate** → summarize ∥ embed → build symbol graph → cleanup. A single `Orchestrator.run(repo_url)` call drives all stages in order, aborting before any LLM/embed spend if the repo exceeds the configured size gates.

## Ownership
- `orchestrator.py` — `Orchestrator` class with `run()` method and `RunResult` dataclass (includes the built `graph`)

## Local Contracts
- Runs stages in fixed dependency order: ingestion → (chunk → summarize ∥ embed) → symbol graph build → cleanup
- **Repo-size gates (usage-cap system, DECISIONS.md D37)**: after scanning, if `len(files) > USAGE_MAX_REPO_FILES` (default 300, `0` disables) it raises `RepoSizeError` before `ensure_repo_indexing` (no `indexed_repo` row, no API spend); after local chunking, if `len(chunks) > USAGE_MAX_REPO_CHUNKS` (default 6000) it raises `RepoSizeError` before embedding/summarization (row exists → `mark_repo_failed`). Both are deliberately checked **before any LLM/embed API call** so a rejected repo costs nothing. The message is user-facing (surfaces via the SSE `{type: error}` event)
- `run(repo_url, on_progress=None)` accepts an optional `on_progress(stage, percent, message)` callback; it fires at each stage boundary (`ingest` 5 → `scan` 15 → `index` 20 → `chunk` 35/50 → `summarize_embed` 60 → `embed` 85 → `graph` 95 → `done` 100) so callers (e.g. the SSE endpoints) can stream progress. The callback is a plain callable; it must not raise
- **Parallel**: after chunking completes (and its gate passes), summarization (per-file LLM) and embedding (per-chunk OpenRouter) run concurrently in a `ThreadPoolExecutor(max_workers=2)` — they consume disjoint inputs (`files` vs `chunks`), each uses its own internal worker pool + DB sessions, so side-by-side execution is thread-safe. Both futures are joined via `as_completed` and the first failure re-raises (same fail semantics as serial; the pool drains before the `with` exits)
- **Chunking completes before any API spend**: chunking is local CPU, so it runs to completion first; only then do summarize/embed (the minutes-long, cost-bearing stages) start. This is what lets the chunk gate reject oversized repos cheaply
- **Normalizes the repo URL at entry** (`core.url.normalize_repo_url`) — the canonical URL is what ingestion stamps on file metadata (`repo_url`), what is stored in `indexed_repo`, and what downstream uses. scp-style/ssh forms are converted to https here, once
- Captures the repo's HEAD commit SHA (`git rev-parse HEAD` on the clone) and returns it as `RunResult.repo_hash` — the durable per-commit identity for `indexed_repo`
- **Clone isolation**: `ingest()` returns `(files, repo_dir)` — `repo_dir` is the unique per-run clone dir (concurrent ingests never share one). The orchestrator reads the commit SHA from that exact dir and always deletes it in `finally` (concurrent-safe rmtree, since the dir is exclusively ours)
- **Creates the `indexed_repo` row (status=`indexing`) as soon as the commit hash is known** (`ensure_repo_indexing`) — required so per-commit artifacts (`file_summary`) can satisfy their FK before summarization persists. The caller finalizes it (`status='indexed'`, counts) after `run()` returns
- On failure after the hash is known, marks the row `failed` (`mark_repo_failed`) and re-raises; the cloned repo dir is always cleaned up (`finally`)
- Summarization is keyed by `repo_hash` (`summarizer.summarize(files, repo_hash)`)
- Builds the repo's symbol graph from the in-memory chunk list (`build_repo_graph_from_chunks`) after embedding succeeds; `RunResult.graph` carries it so the caller persists it (e.g. `backend/main.py` → `repo_graph` table)
- Returns `RunResult` with repo name, URL, hash, file count, chunk count, and the graph
- Exceptions propagate to the caller — no internal error handling (aside from repo-dir cleanup + failed-status marking)
- Does NOT manage UI state, markers, or index state files; DB persistence beyond the `indexed_repo` lifecycle (via `ensure_repo_indexing`/`mark_repo_failed`) is the caller's responsibility

## Work Guidance
- Adding a new pipeline stage requires adding it to `Orchestrator.run()` in the correct position
- The orchestrator is stateless and reusable across calls

## Verification
- Integration tested via `python tests/test_03_embedding.py` (full pipeline)
- Graph path smoke-tested via `build_repo_graph_from_chunks` on synthetic chunks

## Child DOX Index
*None*
