# reranking/

## Purpose
Reranking of hybrid retrieval candidates via OpenRouter API using `cohere/rerank-4-fast`.

## Ownership
- `openrouter_reranker.py` — OpenRouter Rerank API wrapper

## Local Contracts
- Takes `(query, documents)` pairs
- Returns scores per document; higher is better
- Runs after RRF fusion and before post-retrieval adjustments
- Requires `OPENROUTER_API_KEY` in `.env`

## Work Guidance
- Changing reranker model must keep input/output interface compatible with `retrieval/retrieval_pipeline.py`

## Verification
- Run `python tests/test_05_retrieval.py`

## Child DOX Index
*None*
