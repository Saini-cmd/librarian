# rag/

## Purpose
Answer generation from retrieved code chunks. Builds context, constructs prompts, calls LLM (DeepSeek via OpenAI-compatible API), and returns answers with citations.

## Ownership
- `types.py` — Shared dataclasses (also includes `HybridCandidate` for retrieval/reranking)
- `llm_client.py` — Unified `ChatOpenAI` wrapper for DeepSeek API
- `answer_generator.py` — End-to-end: context build → prompt build → LLM call → citation map
- `context_builder.py` — Deduplication, token budget enforcement, line-span overlap removal
- `prompt_builder.py` — LCEL-based prompt construction

## Local Contracts
- Model: configured via `DEEPSEEK_MODEL` env var (default `deepseek-chat`)
- Token budget: 14,000 tokens for context
- Citations include repo, file path, and line numbers
- Citations are mapped only from `[C1]`-style markers the LLM actually emits (`_map_citations`); no sources are appended when the answer cites nothing
- Single unified pipeline

## Work Guidance
- Changing the LLM provider requires updating `llm_client.py` and `.env` schema

## Verification
- Run `python tests/test_07_answer_generation.py`

## Child DOX Index
*None*
