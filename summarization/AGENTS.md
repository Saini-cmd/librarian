# summarization/

## Purpose
Generates per-file summaries (~100 words) using the same LLM as answer generation (DeepSeek via ChatOpenAI). Summaries are stored in PostgreSQL (`file_summaries` table) and injected into the prompt context at answer-generation time to aid LLM inference.

## Ownership
- `summarization_pipeline.py` — Orchestrator: deduplicate files → parallel LLM calls → save via `SummaryStore`
- `file_summarizer.py` — Per-file LLM summary generation with input truncation (~3000 tokens)
- `summary_store.py` — DB-backed store (`SessionLocal`), static interface `exists/save/load/get`

## Local Contracts
- Summaries stored as `(repo_name, file_path, summary_text)` rows in `file_summaries`
- Idempotent: skips if the repo already has summaries in the DB
- Parallel: up to 5 concurrent LLM calls via `ThreadPoolExecutor`
- Truncates file content to ~3000 tokens before summarization
- Failed summaries are skipped (logged, not crashed)
- Static interface preserved so `rag/prompt_builder.py` and tests load summaries unchanged

## Work Guidance
- Changing the summarization model requires updating `LLMConfig` defaults in `rag/types.py`
- Requires local PostgreSQL running (`docker compose up -d postgres`)

## Verification
- Run `python tests/test_08_summarization.py`

## Child DOX Index
*None*
