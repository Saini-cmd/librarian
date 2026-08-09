# chunking/

## Purpose
Converts source files into semantic `CodeChunk` objects using AST-based (Tree-sitter) and text-based strategies (LangChain TokenTextSplitter). No pickle saves or LLM summaries.

## Ownership
- `chunk_model.py` — `CodeChunk` dataclass definition (`repo_url` = canonical repo URL, `repo_hash` = per-commit identity, `qualified_name`/`parent_symbol` = symbol-graph metadata)
- `ast_chunker.py` — Tree-sitter AST traversal for function/class/method extraction; `node_name()` (generic `name` field + language-specific cases: C/C++ fn declarators, Go `type_spec`, Ruby class/module constant + method identifier, Rust `impl_item` → `User`/`User::Fly`), `collect_tree_nodes` (threads the named-ancestor chain), `.tsx` files parsed with the `tsx` grammar via a `parser_language` override (label stays `typescript`)
- `text_chunker.py` — LangChain `TokenTextSplitter` for non-code files
- `chunk_pipeline.py` — Orchestrator: routes files to correct chunker, returns chunks directly; expects `file_metadata["repo_url"]` + `file_metadata["repo_hash"]` pre-populated by ingestion/orchestration
- `parser_manager.py` — Manages Tree-sitter Language objects for 12 languages
- `ast_config.py` — Language→AST node type mappings
- `splitter.py` — Token-aware text splitter (tiktoken-based) for large AST nodes

## Local Contracts
- Supports 12 AST languages: Python, JS, TS, Java, Kotlin, Go, Rust, C, C++, C#, Ruby
- Non-AST files fall back to LangChain `TokenTextSplitter` (420 tokens, 50 token overlap)
- `CodeChunk` fields: `repo_url` (canonical repo URL, display/scoping metadata) + `repo_hash` (commit identity) — preserved through embedding → retrieval → RAG pipeline
- `symbol` is the **bare** declaration name (drives embed text / BM25; unchanged for languages that already extracted names). `qualified_name` (dotted ancestor chain, e.g. `Walker.walk`) + `parent_symbol` (nearest named ancestor, e.g. `Walker`) are graph-only and are **not** part of embed text — populated only for AST chunks
- Ruby wanted set is `{class, module, method}` (tree-sitter-ruby's node type is `method`, not `def`; `class`/`module` names are `constant` children)
- `collect_tree_nodes` stops at the first wanted node, so nested wanted nodes (methods inside classes/impls) are subsumed into the nearest wanted ancestor's chunk
- No pickle files or LLM summaries generated during chunking

## Work Guidance
- Adding a new AST language requires updating `ast_config.py`, `parser_manager.py`, and `constants.py` (ingestion)
- Adding a node type whose name is not a `name` field requires a case in `node_name()`
- Removing tiktoken-based splitter requires updating `ast_chunker.py`

## Verification
- Run `python tests/test_02_chunking.py`

## Child DOX Index
*None*
