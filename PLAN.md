# Librarian AI — Project Plan & Architecture

## Current Pipeline

```
                     orchestration/
                         │
 Orchestrator.run(repo_url)
     │
     ├── ingestion/        git clone --depth 1 → scan → classify files
     │                       stamps `repo` on each file's metadata
     ├── chunking/         AST-based (Tree-sitter) + text chunking → CodeChunks
     │                       reads `repo` from metadata (stamped by ingestion)
     ├── summarization/    LLM per-file summaries (~100 words) via DeepSeek
     │                       parallel (5 workers), idempotent, stores JSON
     ├── embedding/        embed via OpenRouter API (BAAI/bge-base-en-v1.5)
     │                       → upsert to Qdrant, idempotent (checks existing)
     └── cleanup           shutil.rmtree(cloned_repo)

 retrieval/ + reranking/   hybrid search: dense + BM25 + RRF + cross-encoder rerank
                           query embedding via same OpenRouter API

 rag/                       context build → prompt build → LLM (DeepSeek via ChatOpenAI)
                           → answer with [C1], [C2] citations

 vector_store/             Qdrant client singleton (cloud/local fallback)
                           vector config, collection upsert, payload deserialization
```

## What Was Removed / Deleted

| Removed | Reason |
|---|---|
| `rag/external/` (entire directory) | Dead — was a second answer-generation mode, no longer needed |
| `rag/local/llm/` (4 files) | Replaced by unified `rag/llm_client.py` (ChatOpenAI → DeepSeek) |
| `rag/local/answer_generator.py` | Moved to `rag/answer_generator.py` |
| `rag/local/context_builder.py` | Moved to `rag/context_builder.py` |
| `rag/local/prompt_builder.py` | Moved to `rag/prompt_builder.py` |
| `rag/local/__init__.py` | No longer needed |
| `embedding/embedder.py` | Replaced by `api_embedder.py` |
| `reranking/bge_reranker.py` | Replaced by `openrouter_reranker.py` |
| `retrieval/query_embedder.py` | Merged into `embedding/api_embedder.py` |
| `retrieval/bge_reranker.py` | Replaced by `reranking/openrouter_reranker.py` |
| `vector_store/search.py` | Dead code |
| `ingestion/repo_cloner.py` | Replaced by rewritten `github_api_fetcher.py` |
| `tests/test_08_external_deepseek_api_call.py` | Dead test for removed external mode |
| `data/summary/` | Empty orphan directory |
| `data/debug_latest_prompt.txt` | Debug artifact |

## Module Details

### ingestion/

| File | Role |
|---|---|
| `github_api_fetcher.py` | `GitHubAPIFetcher` — `git clone --depth 1`, optional `GITHUB_TOKEN` auth |
| `file_scanner.py` | `FileScanner` — walks repo, classifies files as ast/text/unknown |
| `constants.py` | Extension maps (12 AST languages + text), ignored dirs/files |
| `ingestion_pipeline.py` | `IngestionPipeline` — fetch → scan → stamp `repo` on metadata |

**Key decisions:**
- Replaced PyGithub REST API with `git clone --depth 1` (faster, no rate limits)
- Repo name parsed from URL and stamped on each file's metadata (`f["repo"] = name`)
- Early-exit if `data/repos/{name}` already exists (skips re-clone)
- Cleanup (rmtree) owned by orchestrator, not ingestion

### chunking/

| File | Role |
|---|---|
| `chunk_model.py` | `CodeChunk` dataclass — the shared contract across all pipeline stages |
| `chunk_pipeline.py` | `ChunkPipeline` — routes files to AST or text chunker |
| `ast_chunker.py` | `ASTChunker` — Tree-sitter AST traversal, extracts functions/classes |
| `ast_config.py` | Language → wanted AST node type mappings (12 languages) |
| `parser_manager.py` | Tree-sitter parser factory (12 language grammars) |
| `splitter.py` | `TokenSplitter` — tiktoken-based line-aware splitter for large AST nodes |
| `text_chunker.py` | `TextChunker` — LangChain TokenTextSplitter (420 tokens, 50 overlap) |

**Key decisions:**
- `chunk_repository()` no longer takes `repo_name` param — reads `file_metadata["repo"]`
- AST chunks get `chunk_source="ast"` with symbol/node_type; gaps get `chunk_source="text"`
- No pickle saves — returns `List[CodeChunk]` directly

### summarization/ (NEW)

| File | Role |
|---|---|
| `summarization_pipeline.py` | `SummarizationPipeline` — dedup files → parallel LLM → save JSON |
| `file_summarizer.py` | `FileSummarizer` — per-file LLM call with 3000-token truncation |
| `summary_store.py` | `SummaryStore` — JSON read/write at `data/summaries/{repo}.json` |

**Key decisions:**
- Uses same DeepSeek API via `LLMClient` (consistent with RAG)
- Parallel with 5 workers via `ThreadPoolExecutor`
- Idempotent — skips if summary file already exists
- Summaries keyed by relative file path (matches `CodeChunk.file_path`)
- Failed summaries skipped (logged, not crashed)

### embedding/

| File | Role |
|---|---|
| `api_embedder.py` | `APIEmbedder` — OpenRouter embedding API, handles chunk + query embedding |
| `embedding_pipeline.py` | `EmbeddingPipeline` — filter existing → embed → upsert to Qdrant |

**Key decisions:**
- Embedding model: `BAAI/bge-base-en-v1.5` (768-dim, Cosine)
- Idempotent — checks `QdrantManager.exists(chunk_id)` before embedding
- Embedding text includes structured metadata (repo, file, symbol, lines)
- Query embedding reuses same `APIEmbedder` instance

### orchestration/ (NEW)

| File | Role |
|---|---|
| `orchestrator.py` | `Orchestrator.run()` — sequential: ingestion → chunking → summarization → embedding → cleanup. Returns `RunResult`. |

### vector_store/

| File | Role |
|---|---|
| `qdrant_client.py` | `QdrantManager` singleton — auto-detects cloud (`QDRANT_URL` + `QDRANT_API_KEY`) vs local (`qdrant_db/`) |
| `schema.py` | Vector config constants — `text_dense` (768-dim, Cosine), `text_sparse` (IDF) |
| `indexer.py` | `VectorIndexer` — collection create/check, upsert, idempotent checks + `chunk_from_payload()` shared function |

**Key decisions:**
- `chunk_from_payload()` lives here (the bridge between Qdrant payloads and `CodeChunk`)
- Previously duplicated in `vector_retriever.py` and `bm25_index.py` — now shared

### retrieval/

| File | Role |
|---|---|
| `retrieval_pipeline.py` | `RetrievalPipeline` — end-to-end orchestration |
| `vector_retriever.py` | `VectorRetriever` — dense vector search in Qdrant |
| `bm25_index.py` | `BM25Index` — BM25 keyword index built from Qdrant payloads |
| `hybrid_retriever.py` | `HybridRetriever` — merges vector + BM25 via RRF |
| `rrf.py` | `reciprocal_rank_fusion()` — pure function |
| `post_retrieval.py` | `PostRetrievalProcessor` — score boosting + deduplication |
| `query_expander.py` | `QueryExpander` — appends static intent terms to queries |

**Key decisions:**
- `HybridCandidate` and `HybridRetrievalResult` moved to `rag/types.py` — shared by retrieval + reranking
- `_chunk_from_payload` replaced with shared `vector_store.indexer.chunk_from_payload()`

### reranking/

| File | Role |
|---|---|
| `openrouter_reranker.py` | `OpenRouterReranker` — cross-encoder rerank via OpenRouter (`cohere/rerank-4-fast`) |

**Key decisions:**
- Imports `HybridCandidate` from `rag/types.py` (not from `retrieval.hybrid_retriever`)
- No reverse dependency on retrieval internals

### rag/

| File | Role |
|---|---|
| `types.py` | Shared dataclasses — `CodeChunk`, `HybridCandidate`, `HybridRetrievalResult`, `RetrievedChunk`, `ContextChunk`, `Citation`, `ContextAssembly`, `PromptPayload`, `LLMConfig`, `LLMResponse`, `AnswerResult` |
| `llm_client.py` | `LLMClient` — ChatOpenAI wrapper for DeepSeek (streaming + non-streaming) |
| `answer_generator.py` | `AnswerGenerator` — context → prompt → LLM → citations |
| `context_builder.py` | `ContextBuilder` — deduplication, token budget, overlap removal |
| `prompt_builder.py` | `PromptBuilder` — LCEL ChatPromptTemplate, injects file summaries |

**Key decisions:**
- Flattened — no more `rag/local/` nesting (was leftover from removed `rag/external/`)
- `LLMClient` uses `ChatOpenAI` pointing at DeepSeek's API (OpenAI-compatible)
- Prompt includes per-file summaries from `summarization/summary_store.py`

### backend/

| File | Role |
|---|---|
| `main.py` | FastAPI app — routes, Pydantic models, APP_STATE, cached pipelines |
| `state.py` | State management — marker files, index state, Q&A markdown, reset |
| `AGENTS.md` | Module documentation |

**Key decisions:**
- `main.py` is a thin controller — delegates pipeline to `orchestration/`
- `state.py` extracted from `main.py` — 8 helper functions + constants moved out
- `REPO_MARKER_FILE` path fixed: `data/chunks/lynko` → `data/chunks/repo_marker.txt`
- Removed dead `_load_index_state()`
- Removed stale `LocalContextBuilder` / `LocalPromptBuilder` aliases
- Removed unused constants: `INDEX_STATE_FILE`, `QA_RESPONSE_FILE`, `REPO_MARKER_FILE` imports

## Remaining Directories (not cleaned up)

| Path | Contents | Status |
|---|---|---|
| `data/repos/` | Cloned git repos (leftover from tests) | Orchestrator cleans after embed; tests leave them |
| `data/chunks/index_state.json` | Which repo is indexed | Written by backend |
| `data/responses/latest.md` | Latest Q&A | Written by backend |
| `data/summaries/` | Per-file LLM summaries | Written by summarization pipeline |
| `qdrant_db/` | Local Qdrant storage | .gitignore'd, fallback only |

## Next Phase: Auth + Chat History

### Stack

| Component | Choice |
|---|---|
| Auth | Clerk (Google + GitHub SSO) |
| Database | Supabase (managed PostgreSQL) |
| ORM | SQLAlchemy (async) |
| Hosting | Self-hosted (old PC) with Supabase for DB |

### Schema

```sql
users (
    id            serial primary key,
    clerk_id      text unique not null,
    email         text,
    name          text,
    created_at    timestamptz default now()
)

conversations (
    id            serial primary key,
    clerk_id      text references users(clerk_id),
    title         text,
    created_at    timestamptz default now(),
    updated_at    timestamptz default now()
)

messages (
    id            serial primary key,
    conversation_id int references conversations(id),
    role          text not null,              -- 'user' | 'assistant'
    content       text not null,
    citations     jsonb,
    created_at    timestamptz default now()
)
```

### New Files

| File | Purpose |
|---|---|
| `backend/database.py` | SQLAlchemy engine, session factory, `get_db` dependency |
| `backend/models.py` | User, Conversation, Message ORM models |
| `backend/auth.py` | Clerk JWT verification middleware |
| `backend/routers/__init__.py` | Router package |
| `backend/routers/auth_webhook.py` | Clerk webhook endpoint for user sync |
| `backend/routers/conversations.py` | CRUD for conversations + messages |

### Changes to Existing Files

| File | Change |
|---|---|
| `backend/main.py` | Add auth middleware, mount routers, replace APP_STATE chat with DB |
| `requirements.txt` | Add `sqlalchemy`, `asyncpg`, `psycopg2-binary`, `alembic`, clerk SDK |
| `.env` | Add `SUPABASE_DATABASE_URL`, `CLERK_SECRET_KEY`, `CLERK_WEBHOOK_SECRET` |
| `frontend/` | Add Clerk React SDK, login/signup UI, pass JWT to API |

### Implementation Order

| Step | What |
|---|---|
| 1 | Add dependencies to `requirements.txt` |
| 2 | Create `backend/database.py` — engine, session, Base |
| 3 | Create `backend/models.py` — User, Conversation, Message |
| 4 | Set up Alembic for migrations |
| 5 | Create `backend/auth.py` — Clerk JWT verification middleware |
| 6 | Create `backend/routers/auth_webhook.py` |
| 7 | Add auth middleware to `backend/main.py`, protect endpoints |
| 8 | Create `backend/routers/conversations.py` |
| 9 | Update chat endpoints to save Q&A to DB |
| 10 | Add Clerk SDK + login UI to frontend |
| 11 | Update frontend to send JWT with API requests |
