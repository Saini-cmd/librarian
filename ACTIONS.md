# Actions — Librarian AI Migration

Tracked from [PLAN.md](PLAN.md). Update status as work progresses.

---

## Phase 1: LLM Clients (DeepSeek via ChatOpenAI) ✅

- [x] Create `rag/llm_client.py` — unified `ChatOpenAI` wrapper (DeepSeek via OpenAI-compatible API)
- [x] Delete `rag/local/llm/ollama_client.py`
- [x] Delete `rag/local/llm/local_summary_client.py`
- [x] Delete `rag/local/llm/openrouter_client.py`
- [x] Delete `rag/external/llm/deepseek_client.py`
- [x] Rewrite `rag/local/answer_generator.py` — use LLMClient
- [x] Rewrite `rag/local/prompt_builder.py` — LCEL ChatPromptTemplate
- [x] Delete `rag/external/context_builder.py`
- [x] Delete `rag/external/prompt_builder.py`
- [x] Delete `rag/external/answer_generator.py`
- [x] Update `requirements.txt` — add `openai`, `langchain-openai`, `langchain-core`
- [ ] Verify: `python tests/test_07_answer_generation.py` (requires Qdrant with indexed data)

## Phase 2: Embedding API (OpenRouter) ✅

- [x] Create `embedding/api_embedder.py` — OpenRouter Embedding API client (`BAAI/bge-base-en-v1.5`, 768-dim)
- [x] Delete `embedding/embedder.py` — local SentenceTransformer
- [x] Delete `retrieval/query_embedder.py` — merged into api_embedder
- [x] Update `embedding/embedding_pipeline.py` — use APIEmbedder
- [x] Update `retrieval/retrieval_pipeline.py` — use APIEmbedder for query embedding
- [x] Update `vector_store/indexer.py` — handle list embeddings
- [x] Update `vector_store/search.py` — use APIEmbedder
- [x] Add `OPENROUTER_API_KEY` to `.env`
- [ ] Verify: `python tests/test_03_embedding.py` (requires API key + Qdrant)

## Phase 3: Reranker API (OpenRouter) ✅

- [x] Create `reranking/openrouter_reranker.py` — OpenRouter Rerank API wrapper (`cohere/rerank-4-fast`)
- [x] Delete `reranking/bge_reranker.py` — local cross-encoder (BAAI/bge-reranker-large)
- [x] Update `retrieval/retrieval_pipeline.py` — use OpenRouterReranker
- [x] Update `backend/main.py` — remove reranker_device param
- [x] Remove `RAG_RERANKER_DEVICE` from `.env`
- [ ] Verify: `python tests/test_05_retrieval.py` (requires API key + Qdrant)

## Phase 4: GitHub API Fetcher ✅

- [x] Create `ingestion/github_api_fetcher.py` — PyGithub, no clone, writes files to disk
- [x] Delete `ingestion/repo_cloner.py` — replaced
- [x] Update `ingestion/ingestion_pipeline.py` — use GitHubAPIFetcher
- [x] Update `requirements.txt` — add `pygithub`, remove `gitpython`
- [x] Uninstall `gitpython`, install `pygithub`
- [ ] Verify: `python tests/test_01_ingestion.py` (requires GitHub API access)

## Phase 5: Qdrant Cloud ✅

- [x] Update `vector_store/qdrant_client.py` — auto-detect cloud (QDRANT_URL + QDRANT_API_KEY) or local fallback
- [x] Add `QDRANT_URL`, `QDRANT_API_KEY` to `.env`

## Phase 6: Strip Pickle Pipeline (Direct Upsert) ✅

- [x] Rewrite `chunking/chunk_pipeline.py` — no pickle saves, no LLM summaries, returns chunks directly
- [x] Rewrite `embedding/embedding_pipeline.py` — accepts chunks directly, embeds via API, upserts (no pickle)
- [x] Replace `chunking/text_chunker.py` — uses LangChain `TokenTextSplitter`
- [x] Rewrite `chunking/splitter.py` — uses `tiktoken` instead of `transformers.AutoTokenizer`
- [x] Update `backend/main.py` — pass chunks directly to embedder
- [ ] Verify: end-to-end `test_03_embedding.py` (requires API keys + Qdrant)

## Phase 7: Chat Memory (Upstash Redis)

- [ ] Create `rag/memory.py` — ChatMemory with Upstash Redis
- [ ] Add `session_id` to chat endpoints in `backend/main.py`
- [ ] Update `rag/local/context_builder.py` — inject memory into context
- [ ] Update `frontend/src/App.jsx` — generate + send `sessionId`
- [ ] Add `UPSTASH_REDIS_URL`, `UPSTASH_REDIS_TOKEN` to `.env`
- [ ] Update `requirements.txt` — add `upstash-redis`
- [ ] Verify: multi-turn chat preserves history

## Phase 8: LangChain/LCEL Compose ✅

- [x] Create `rag/embeddings.py` — LangChain `Embeddings` interface wrapping OpenRouter API
- [x] Update `retrieval/bm25_index.py` — uses `BM25Retriever` from langchain-community
- [x] Create `vector_store/langchain_store.py` — `QdrantVectorStore` factory with `LLMEmbeddings`
- [x] Update `requirements.txt` — add `langchain-community`, `langchain-qdrant`
- [x] Verify: full pipeline imports and embedding wrapper functional
- [ ] LangServe routes — deferred (Phase 9 deployment)
- [ ] Full Document type migration — deferred (keeps CodeChunk at boundaries)

## Phase 9: Deploy

- [ ] Backend: deploy to Render (free tier)
- [ ] Frontend: deploy to Vercel or Cloudflare Pages
- [ ] Set all environment variables in hosting dashboard
- [ ] Add `.env.example` with all required keys
- [ ] Verify: production chat round-trip
