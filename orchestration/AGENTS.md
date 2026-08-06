# orchestration/

## Purpose
Orchestrates the full ingestion pipeline: clone → chunk → summarize → embed → build symbol graph → cleanup. A single `Orchestrator.run(repo_url)` call drives all stages sequentially.

## Ownership
- `orchestrator.py` — `Orchestrator` class with `run()` method and `RunResult` dataclass (includes the built `graph`)

## Local Contracts
- Runs stages in fixed order: ingestion → chunking → summarization → embedding → symbol graph build → cleanup
- Builds the repo's symbol graph from the in-memory chunk list (`build_repo_graph_from_chunks`) after embedding succeeds; `RunResult.graph` carries it so the caller persists it (e.g. `backend/main.py` → `repo_graphs` table)
- Cleans up cloned repo after embedding + graph build succeed
- Returns `RunResult` with repo name, file count, chunk count, and the graph
- Exceptions propagate to the caller — no internal error handling
- Does NOT manage UI state, markers, index state files, or DB persistence — those are the caller's responsibility

## Work Guidance
- Adding a new pipeline stage requires adding it to `Orchestrator.run()` in the correct position
- The orchestrator is stateless and reusable across calls

## Verification
- Integration tested via `python tests/test_03_embedding.py` (full pipeline)
- Graph path smoke-tested via `build_repo_graph_from_chunks` on synthetic chunks

## Child DOX Index
*None*
