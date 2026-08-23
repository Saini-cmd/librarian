# rag/

## Purpose
Answer generation from retrieved code chunks. Builds context, constructs prompts, calls LLM (DeepSeek via OpenAI-compatible API), and returns answers with citations.

## Ownership
- `types.py` — Shared dataclasses (also includes `HybridCandidate` for retrieval/reranking)
- `llm_client.py` — Unified `ChatOpenAI` wrapper for DeepSeek API
- `answer_generator.py` — End-to-end: context build → prompt build → LLM call → citation map
- `context_builder.py` — Deduplication, token budget enforcement, line-span overlap removal
- `prompt_builder.py` — Prompt construction: RAG context + conversation history (multi-turn `user`/`assistant`) + long-term memory injection (prompt text imported from `core/prompts.py`)

## Local Contracts
- Model: configured via `DEEPSEEK_MODEL` env var (default `deepseek-chat`)
- Token budget: 14,000 tokens for context
- **Multi-turn**: `PromptBuilder.build(query, context, repo_hash, history, memory_texts)` emits `system` → alternating `user`/`assistant` history turns → final `human` (repo hint + long-term memory + RAG context + query). `LLMClient._to_langchain` maps `assistant` → `AIMessage` (multi-turn support). `AnswerGenerator.generate(..., history=, memory_texts=)` threads them through
- Long-term memory is injected as raw text (never citable) — `RAG_MEMORY_GUIDANCE` (in `core/prompts.py`) appended to the system prompt only when memory is present; citations map exclusively to retrieved context chunks
- Citations include repo, file path, line numbers, and `repo_hash` (stable file-identity resolution — `chunk_id` is metadata only, so citations survive sync)
- Summaries loaded by `repo_hash` (`SummaryStore.load(repo_hash)`), threaded from the conversation via `PromptBuilder.build(..., repo_hash=...)` and `AnswerGenerator.generate(..., repo_hash=...)`
- Citations are mapped only from `[C1]`-style markers the LLM actually emits (`_map_citations`); no sources are appended when the answer cites nothing
- Single unified pipeline

## Work Guidance
- Changing the LLM provider requires updating `llm_client.py` and `.env` schema
- History/memory come from `memory/` (`build_memory_context`) — the read path stays zero-LLM (history + raw memory go straight into the prompt)

## Verification
- Run `python tests/test_07_answer_generation.py`

## Child DOX Index
*None*
