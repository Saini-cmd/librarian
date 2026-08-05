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
- No intermediate pickle files — chunks go directly from chunker to embedder
- Requires `OPENROUTER_API_KEY` in `.env`

## Work Guidance
- Changing embedding model requires updating `retrieval/retrieval_pipeline.py` to match
- Pipeline must be idempotent (skip already-embedded chunks via Qdrant lookup)

## Verification
- Run `python tests/test_03_embedding.py`

## Child DOX Index
*None*
