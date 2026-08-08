# orchestration/

## Purpose
Orchestrates the full ingestion pipeline: clone → chunk → summarize → embed → build symbol graph → cleanup. A single `Orchestrator.run(repo_url)` call drives all stages sequentially.

## Ownership
- `orchestrator.py` — `Orchestrator` class with `run()` method and `RunResult` dataclass (includes the built `graph`)

## Local Contracts
- Runs stages in fixed dependency order: ingestion → (summarization ∥ chunking → embedding) → symbol graph build → cleanup
- `run(repo_url, on_progress=None)` accepts an optional `on_progress(stage, percent, message)` callback; it fires at each stage boundary (`ingest` 5 → `scan` 15 → `index` 20 → `chunk` 35/50 → `summarize_embed` 60 → `embed` 85 → `graph` 95 → `done` 100) so callers (e.g. the SSE endpoints) can stream progress. The callback is a plain callable; it must not raise
- **Parallel**: after scanning, summarization (slow per-file LLM) runs in a worker thread while chunking → embedding proceed in the main thread — both consume only `files`, so there is no ordering dependency. The orchestrator joins the summary task before building the graph; a summarization exception re-raises via `future.result()` (same fail semantics as serial)
- **Normalizes the repo URL at entry** (`backend.state.normalize_repo_url`) — the canonical URL is what ingestion stamps on file metadata (`repo_url`), what is stored in `indexed_repo`, and what downstream uses. scp-style/ssh forms are converted to https here, once
- Captures the repo's HEAD commit SHA (`git rev-parse HEAD` on the clone) and returns it as `RunResult.repo_hash` — the durable per-commit identity for `indexed_repo`
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
