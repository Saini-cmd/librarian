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
- No intermediate pickle files — chunks go directly from chunker to embedder
- Requires `OPENROUTER_API_KEY` in `.env`

## Work Guidance
- Changing embedding model requires updating `retrieval/retrieval_pipeline.py` to match
- Pipeline must be idempotent (skip already-embedded chunks via Qdrant lookup)

## Verification
- Run `python tests/test_03_embedding.py`

## Child DOX Index
*None*
