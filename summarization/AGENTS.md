# summarization/

## Purpose
Generates per-file summaries (~100 words) using a cheap shared summarization model (OpenRouter `inclusionai/ling-3.0-flash`), distinct from the answer-generation LLM. Summaries are stored in PostgreSQL (`file_summary` table) and injected into the prompt context at answer-generation time to aid LLM inference. The same shared config powers the chat-memory rolling summaries (`memory/worker.py`).

## Ownership
- `summarization_pipeline.py` — Orchestrator: deduplicate files → parallel LLM calls → save via `SummaryStore`
- `file_summarizer.py` — Per-file LLM summary generation with input truncation (~3000 tokens); prompt text in root `prompts.py`
- `llm_config.py` — `build_summarizer_config()`: shared OpenRouter `ling-3.0-flash` `LLMConfig` from `SUMMARIZE_*` env (model/base_url/api-key/max-tokens); `SUMMARIZE_API_KEY` falls back to `OPENROUTER_API_KEY`
- `summary_store.py` — DB-backed store (`SessionLocal`), static interface `exists/save/load/get`

## Local Contracts
- Summaries stored as `(repo_hash, file_path, summary_text)` rows in `file_summary` — keyed by the repo **commit hash**, not the repo name
- **Model is NOT the answer LLM**: `FileSummarizer` uses `LLMClient(build_summarizer_config())` — OpenRouter `inclusionai/ling-3.0-flash` (~10-17x cheaper than DeepSeek-chat), OpenAI-compatible `https://openrouter.ai/api/v1`. Flip back by setting `SUMMARIZE_MODEL`/`SUMMARIZE_BASE_URL`/`SUMMARIZE_API_KEY` (one env change); the chat answer LLM stays DeepSeek
- Idempotent: skips if the commit already has summaries in the DB
- Parallel: up to 5 concurrent LLM calls via `ThreadPoolExecutor` (`SUMMARIZE_CONCURRENCY`, default 5)
- **Retry with backoff**: transient failures (e.g. OpenRouter 429 rate limiting on the cheap model) are retried per file with exponential backoff (2s, 4s, ...) up to `SUMMARIZE_MAX_ATTEMPTS` (default 3); only a failure after all attempts is skipped (logged once with traceback, not crashed). Non-transient file errors are retried too (bounded)
- Truncates file content to ~3000 tokens before summarization
- Failed summaries are skipped after exhausting retries (logged, not crashed)
- Static interface preserved so `rag/prompt_builder.py` and tests load summaries unchanged

## Work Guidance
- Changing the summarization model requires updating `SUMMARIZE_*` in `.env` (documented in `.env.example`) — the same knobs drive the chat-memory `rollup_session_summary` in `memory/worker.py`
- Requires local PostgreSQL running (`docker compose up -d postgres`)

## Verification
- Run `python tests/test_08_summarization.py`
- Config unit check: `build_summarizer_config()` returns OpenRouter `ling-3.0-flash`

## Child DOX Index
*None*
