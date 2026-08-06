# vector_store/

## Purpose
Qdrant client singleton and vector management. Default is a local Dockerized Qdrant server (`QDRANT_MODE=server`); cloud and embedded modes are kept dormant for parallel development.

## Ownership
- `qdrant_client.py` — `QdrantManager` singleton resolving `QDRANT_MODE` (server / cloud / embedded)
- `schema.py` — Named vector config (`text_dense`) and sparse vector config (`text_sparse`)
- `indexer.py` — `VectorIndexer`: create collection, check existence, upsert points

## Local Contracts
- `QDRANT_MODE=server` (default): connects to `QDRANT_LOCAL_URL` (default `http://localhost:6333`, Dockerized `qdrant/qdrant`)
- Docker image pinned to `qdrant/qdrant:v1.17.0` to match installed `qdrant-client` 1.17.0 — client/server minor version diff must stay ≤ 1
- `QDRANT_MODE=cloud` (dormant): `QDRANT_URL` + `QDRANT_API_KEY`
- `QDRANT_MODE=embedded` (dormant): in-process `qdrant_db/` file store
- Collection name: `code_chunks`
- Dense vector: `text_dense` (768-dim, Cosine)
- Sparse vector: `text_sparse` defined in schema (idf modifier)
- Payload includes full chunk metadata for BM25 and citation use

## Work Guidance
- Changing vector dimensions requires wiping Qdrant and re-embedding all chunks
- Use `VectorIndexer.exists()` for idempotent upsert
- Start the local server with `docker compose up -d qdrant`
- Changing embedding model requires updating `retrieval/retrieval_pipeline.py` to match

## Verification
- Run `python tests/test_04_view_embedding.py`

## Child DOX Index
*None*
