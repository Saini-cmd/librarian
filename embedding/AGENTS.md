# embedding/

## Purpose
Embeds `CodeChunk` objects via OpenRouter API (`BAAI/bge-base-en-v1.5`) and upserts vectors to Qdrant. Skips already-indexed chunks for incremental ingestion. Also provides query embedding for retrieval.

## Ownership
- `api_embedder.py` — OpenRouter Embedding API client with `embed_texts`, `embed_chunks`, `embed_query`
- `embedding_pipeline.py` — Accepts chunks directly → filter existing → embed via API → upsert

## Local Contracts
- Embedding dimension: 768 (`BAAI/bge-base-en-v1.5`)
- Distance metric: Cosine
- Embedding text format includes structured metadata (repo, file, language, symbol, lines)
- Input truncated to ≤505 BGE tokens using the model's own tokenizer (`transformers` AutoTokenizer); falls back to a 400-token tiktoken estimate if the tokenizer is unavailable — required because BGE tokenizes code more aggressively than cl100k and rejects inputs >512 tokens
- Inputs are batched to ≤256 texts per request (`EMBED_BATCH_SIZE`) — OpenRouter's embeddings endpoint rejects input arrays over 1024 items (`array_above_max_length`); embeddings are concatenated in batch order so chunk↔vector mapping stays aligned
- **Parallel**: embedding API batches fan out to up to `EMBED_MAX_WORKERS` (5) concurrent `_embed_batch` calls via `ThreadPoolExecutor` (matching summarization's concurrency); results are collected by batch index so order is preserved. A batch failure raises (pending futures are awaited on pool shutdown)
- Transient failures (`429`/`500`/`502`/`503`/`504`) are retried with exponential backoff (3 attempts, base delay 1s); non-retryable statuses raise immediately
- No intermediate pickle files — chunks go directly from chunker to embedder
- Requires `OPENROUTER_API_KEY` in `.env`

## Work Guidance
- Changing embedding model requires updating `retrieval/retrieval_pipeline.py` to match
- Pipeline must be idempotent (skip already-embedded chunks via Qdrant lookup)

## Verification
- Run `python tests/test_03_embedding.py`

## Child DOX Index
*None*
