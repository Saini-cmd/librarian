# Plan — Embed-API outage resilience (BM25-only fallback)

> STATUS: **DONE** — implemented in `retrieval/retrieval_pipeline.py`, verified
> via stub smoke (embed raises → BM25-only results, no crash; normal path
> unchanged), DOX pass done (`retrieval/AGENTS.md`, `DECISIONS.md` D38,
> `TODO.md`).

## Context / root cause

The backend logged a 500 on `POST /api/chat/stream` caused by a **transient DNS
failure resolving `openrouter.ai`** (`socket.gaierror [Errno -2]`) during the
query-embedding call. Verified the domain resolves now — it was a network blip,
**not** related to the usage-cap work.

The outage surfaced in two places:
- Long-term memory (`memory/short_term.py:89`) → **degrades gracefully** ("degrading to no memory"). OK.
- Main retrieval (`retrieval/retrieval_pipeline.py:66` → `embed_query`) → **raises → 500** on chat/chat-stream. BAD.

`retrieve()` calls `query_embedder.embed_query()` with no guard. This is
inconsistent with the project's own resilience philosophy: D13 already made
rerank failure degrade to hybrid, and chat memory degrades to no-memory.

## Decision (approved scope: BM25-only fallback only)

Make `RetrievalPipeline.retrieve` degrade to **BM25-only keyword retrieval**
(local, Qdrant-backed — no external API) when query embedding fails, so chat
never 500s on an embed-API outage. Covers both `/api/chat` and `/api/chat/stream`
(shared `retrieve()`).

NOT in scope (per user): mirroring into eval S4, and guarding non-streaming
`/api/chat` generation against DeepSeek outages.

## Implementation — `retrieval/retrieval_pipeline.py`

1. Import: add `HybridRetrievalResult` to the `rag.types` import line.
2. In `retrieve()`, wrap the embed + hybrid-retrieve in `try/except`:

```python
try:
    query_vector = self.query_embedder.embed_query(expanded_query)
    retrieval_result = self.hybrid_retriever.retrieve(
        query=expanded_query, query_vector=query_vector, repo_hash=repo_hash
    )
    degraded = None
except Exception:
    logger.warning(
        "stage=query_embed_failed falling_back_to_bm25_only hash=%s",
        repo_hash or "all",
        exc_info=True,
    )
    degraded = "bm25_only"
    bm25_results = self.bm25_index.search(expanded_query, repo_hash=repo_hash)
    retrieval_result = HybridRetrievalResult(
        candidates=[
            HybridCandidate(
                chunk=r["chunk"],
                rrf_score=float(r.get("score") or 0.0),
                vector_score=None,
                bm25_score=float(r.get("score") or 0.0),
            )
            for r in bm25_results
        ],
        vector_count=0,
        bm25_count=len(bm25_results),
    )
```

   Notes:
   - `bm25_index.search` without `top_k` uses the index's configured `top_k`
     (same value the pipeline passes as `bm25_top_k`).
   - `adjust_scores` only needs `rrf_score` (verified) — setting it to the BM25
     score keeps the existing post-processing pipeline valid.
   - No new attributes needed on `__init__`.
3. The existing rerank `try/except` stays as-is (during the same outage it also
   fails → returns `deduped_candidates[:final_top_k]`, `reranked: False`).
4. After the rerank block, tag degraded results:

```python
if degraded:
    for item in final_results:
        item["degraded"] = degraded
```

## Verification

- Stub smoke (no API): monkeypatch `RetrievalPipeline.query_embedder.embed_query`
  to raise `ConnectionError`, patch `bm25_index.search` to return a few synthetic
  results → assert `retrieve()` returns BM25-only candidates with
  `reranked=False` and `degraded="bm25_only"` instead of raising.
- Normal path unchanged: stub embed to succeed → assert hybrid+rerank flow intact.
- Import check: `backend.main` imports cleanly.

## DOX pass

- `retrieval/AGENTS.md`: add a Local Contracts bullet — query-embed failure
  degrades to BM25-only (local, Qdrant-backed), tagging results `degraded:
  "bm25_only"`, consistent with the D13 rerank fallback.
- `DECISIONS.md`: D38 entry (extend D13's degrade-don't-crash philosophy to
  query embedding; alternatives: let chat 500 on embed outage, degrade to empty
  results).
- `TODO.md`: note the resilience item under the usage-cap section or housekeeping.
