# vector_store/

## Purpose
Qdrant client singleton and vector management. Supports both local on-disk and Qdrant Cloud modes.

## Ownership
- `qdrant_client.py` — `QdrantManager` singleton wrapping `QdrantClient` (auto-detects cloud vs local)
- `schema.py` — Named vector config (`text_dense`) and sparse vector config (`text_sparse`)
- `indexer.py` — `VectorIndexer`: create collection, check existence, upsert points

## Local Contracts
- Cloud mode when `QDRANT_URL` + `QDRANT_API_KEY` are set; falls back to local `qdrant_db/`
- Collection name: `code_chunks`
- Dense vector: `text_dense` (768-dim, Cosine)
- Sparse vector: `text_sparse` defined in schema (idf modifier)
- Payload includes full chunk metadata for BM25 and citation use

## Work Guidance
- Changing vector dimensions requires wiping Qdrant and re-embedding all chunks
- Use `VectorIndexer.exists()` for idempotent upsert

## Verification
- Run `python tests/test_04_view_embedding.py`

## Child DOX Index
*None*
