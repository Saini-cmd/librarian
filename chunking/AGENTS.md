# chunking/

## Purpose
Converts source files into semantic `CodeChunk` objects using AST-based (Tree-sitter) and text-based strategies (LangChain TokenTextSplitter). No pickle saves or LLM summaries.

## Ownership
- `chunk_model.py` — `CodeChunk` dataclass definition (`repo_url` = canonical repo URL, `repo_hash` = per-commit identity)
- `ast_chunker.py` — Tree-sitter AST traversal for function/class/method extraction
- `text_chunker.py` — LangChain `TokenTextSplitter` for non-code files
- `chunk_pipeline.py` — Orchestrator: routes files to correct chunker, returns chunks directly; expects `file_metadata["repo_url"]` + `file_metadata["repo_hash"]` pre-populated by ingestion/orchestration
- `parser_manager.py` — Manages Tree-sitter Language objects for 12 languages
- `ast_config.py` — Language→AST node type mappings
- `splitter.py` — Token-aware text splitter (tiktoken-based) for large AST nodes

## Local Contracts
- Supports 12 AST languages: Python, JS, TS, Java, Kotlin, Go, Rust, C, C++, C#, Ruby
- Non-AST files fall back to LangChain `TokenTextSplitter` (420 tokens, 50 token overlap)
- `CodeChunk` fields: `repo_url` (canonical repo URL, display/scoping metadata) + `repo_hash` (commit identity) — preserved through embedding → retrieval → RAG pipeline
- No pickle files or LLM summaries generated during chunking

## Work Guidance
- Adding a new AST language requires updating `ast_config.py`, `parser_manager.py`, and `constants.py` (ingestion)
- Removing tiktoken-based splitter requires updating `ast_chunker.py`

## Verification
- Run `python tests/test_02_chunking.py`

## Child DOX Index
*None*
