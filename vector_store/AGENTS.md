# vector_store/

## Purpose
Qdrant client singleton and vector management. Default is a local Dockerized Qdrant server (`QDRANT_MODE=server`); cloud and embedded modes are kept dormant for parallel development.

## Ownership
- `qdrant_client.py` — `QdrantManager` singleton resolving `QDRANT_MODE` (server / cloud / embedded)
- `schema.py` — Named vector config (`text_dense`) and sparse vector config (`text_sparse`)
- `indexer.py` — `VectorIndexer`: create collection, check existence, upsert points; `delete_points_by_repo_hash` module helper; `scroll_chunks_by_file` module helper (all chunks for one file in a commit via `repo_hash` + `file_path` filter, sorted by line span — used to reconstruct a file's full source)

## Local Contracts
- `QDRANT_MODE=server` (default): connects to `QDRANT_LOCAL_URL` (default `http://localhost:6333`, Dockerized `qdrant/qdrant`)
- Docker image pinned to `qdrant/qdrant:v1.17.0` to match installed `qdrant-client` 1.17.0 — client/server minor version diff must stay ≤ 1
- `QDRANT_MODE=cloud` (dormant): `QDRANT_URL` + `QDRANT_API_KEY`
- `QDRANT_MODE=embedded` (dormant): in-process `qdrant_db/` file store
- Collection name: `code_chunks`
- Dense vector: `text_dense` (768-dim, Cosine)
- Sparse vector: `text_sparse` defined in schema (idf modifier)
- **Hash-only scoping**: payload carries `repo_url` (canonical repo URL, display) + `repo_hash` (globally-unique commit identity); all Qdrant reads and deletes filter by `repo_hash` alone — no `repo`/URL name filter
- Payload also carries `qualified_name` + `parent_symbol` (graph-only symbol metadata, additive); `chunk_from_payload` reads them via `.get` (defaults `""`) so pre-existing points without the keys stay valid
- `chunk_from_payload` reads `repo_url` (Qdrant is hash-only, so no legacy `repo` key fallback), returns `CodeChunk | None`
- `VectorIndexer.delete_by_repo_hash(repo_hash, keep_chunk_ids=None)` and module-level `delete_points_by_repo_hash(repo_hash, keep_chunk_ids, collection_name)` delete all of a commit's points except cited chunk ids (`must_not` on `chunk_id`) — used by sync cleanup

## Work Guidance
- Changing vector dimensions requires wiping Qdrant and re-embedding all chunks
- Use `VectorIndexer.exists()` for idempotent upsert
- Start the local server with `docker compose up -d qdrant`
- Changing embedding model requires updating `retrieval/retrieval_pipeline.py` to match

## Verification
- Run `python tests/test_04_view_embedding.py`

## Child DOX Index
*None*
