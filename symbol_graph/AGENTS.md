# symbol_graph/

## Purpose
Builds a symbol graph for an indexed repo from its AST chunks in Qdrant: nodes for files and entities (class/function/method/interface), edges showing where each entity is defined, referenced by other entities, and used across files. Serves the frontend Graph view.

## Ownership
- `graph_builder.py` — `build_repo_graph(repo_name)`, `clear_graph_cache()`, `_load_repo_chunks`, reference-edge detection

## Local Contracts
- Reads `code_chunks` via Qdrant `scroll` with a `repo` payload filter (same pattern as retrieval BM25)
- Only `chunk_source == "ast"` chunks with a symbol (len >= 2) become entity nodes; deduped by `(file, symbol)`
- JS/TS arrow-function / function-expression components (`const X = () => …`, `export const X = function …`, class expressions) are NOT AST chunks, so they are synthesized as entities from JS/TS text chunks via `_js_component_declarations` (module-level `variable_declarator` with a function/class expression value; nested/boundary nodes skipped); an existing AST entity for the same `(file, symbol)` wins
- File nodes are created for every file in the repo (AST and text chunks) so all `defines`/`used_in` edge targets exist; edges are filtered at output to drop self-loops or references to missing node ids (this keeps d3-force from throwing on dangling links)
- Node schema: `{id, label, kind, file, language, start_line, end_line, content?}`; kinds map from `node_type` via `KIND_MAP` (`class`/`interface`/`impl`/`method`/`function`/`entity`/`file`)
- Content snippet capped at `MAX_SNIPPET_CHARS` (4000) — Qdrant chunk content is the only surviving code (source dir cleaned post-ingest)
- Edge schema: `{source, target, type}`; types: `defines` (entity → file), `uses` (entity → entity reference), `used_in` (entity → other file whose text references it)
- Reference detection parses each chunk's code with tree-sitter (`ParserManager`, per-language parser cache) and collects nodes whose type ends in `identifier` (identifier/type_identifier/field_identifier/...); a symbol is linked only when its name appears as an identifier in another chunk's code — comments/strings/docs never count
- `build_repo_graph` is `lru_cache`d per repo name; `clear_graph_cache()` must be called on reset
- Result shape: `{repo, nodes, edges}`

## Work Guidance
- If AST `node_type` values change in `chunking/ast_config.py`, extend `KIND_MAP`
- Keep the builder pure — no DB/auth logic here; endpoints live in `backend/routers/repositories.py`

## Verification
- Smoke test: `python -c "from symbol_graph.graph_builder import build_repo_graph; g = build_repo_graph('<repo>'); print(len(g['nodes']), len(g['edges']))"`

## Child DOX Index
*None*
