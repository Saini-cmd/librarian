# orchestration/

## Purpose
Orchestrates the full ingestion pipeline: clone → chunk → summarize → embed → cleanup. A single `Orchestrator.run(repo_url)` call drives all stages sequentially.

## Ownership
- `orchestrator.py` — `Orchestrator` class with `run()` method and `RunResult` dataclass

## Local Contracts
- Runs stages in fixed order: ingestion → chunking → summarization → embedding
- Cleans up cloned repo after embedding succeeds
- Returns `RunResult` with repo name, file count, and chunk count
- Exceptions propagate to the caller — no internal error handling
- Does NOT manage UI state, markers, or index state files — those are the caller's responsibility

## Work Guidance
- Adding a new pipeline stage requires adding it to `Orchestrator.run()` in the correct position
- The orchestrator is stateless and reusable across calls

## Verification
- Integration tested via `python tests/test_03_embedding.py` (full pipeline)

## Child DOX Index
*None*
