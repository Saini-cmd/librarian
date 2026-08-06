# retrieval/

## Purpose
Hybrid retrieval pipeline combining dense vector search and BM25 keyword search with Reciprocal Rank Fusion, followed by cross-encoder reranking and score adjustments.

## Ownership
- `retrieval_pipeline.py` — End-to-end orchestration
- `vector_retriever.py` — Dense vector search in Qdrant
- `bm25_index.py` — BM25 index built from Qdrant payloads
- `hybrid_retriever.py` — Merges vector + BM25 results via RRF
- `query_expander.py` — Query expansion with intent terms
- `post_retrieval.py` — Score boosting/penalizing by directory patterns
- `rrf.py` — Reciprocal Rank Fusion implementation

## Local Contracts
- Dense + BM25 → RRF → rerank → post-process pipeline order
- Query embedding via `embedding.api_embedder.APIEmbedder` (OpenRouter API)
- BM25 index built from Qdrant payloads and cached per repo (plus one shared all-repo index)
- Retrieval scoped to a single repo via `repo_name` (Qdrant `repo` payload `FieldCondition` filter applied to both dense and BM25 paths); `repo_name=None` searches everything
- Post-retrieval boosts `src/`, `lib/`, `core/`; penalizes `test/`, `docs/`, `examples/`

## Work Guidance
- N/A

## Verification
- Run `python tests/test_05_retrieval.py`

## Child DOX Index
*None*
