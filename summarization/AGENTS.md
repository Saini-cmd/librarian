# summarization/

## Purpose
Generates per-file summaries (~100 words) using the same LLM as answer generation (DeepSeek via ChatOpenAI). Summaries are stored in `data/summaries/{repo_name}.json` and injected into the prompt context at answer-generation time to aid LLM inference.

## Ownership
- `summarization_pipeline.py` — Orchestrator: deduplicate files → parallel LLM calls → save to JSON store
- `file_summarizer.py` — Per-file LLM summary generation with input truncation (~3000 tokens)
- `summary_store.py` — JSON read/write for `data/summaries/{repo_name}.json`

## Local Contracts
- Summaries stored as `{relative_file_path: summary_text}` in JSON per repo
- Idempotent: skips if `data/summaries/{repo_name}.json` already exists
- Parallel: up to 5 concurrent LLM calls via `ThreadPoolExecutor`
- Truncates file content to ~3000 tokens before summarization
- Failed summaries are skipped (logged, not crashed)

## Work Guidance
- Changing the summarization model requires updating `LLMConfig` defaults in `rag/types.py`

## Verification
- Run `python tests/test_08_summarization.py`

## Child DOX Index
*None*
