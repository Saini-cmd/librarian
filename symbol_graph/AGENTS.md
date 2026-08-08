# symbol_graph/

## Purpose
Builds a symbol graph for an indexed repo from its AST chunks: nodes for files and entities (class/function/method/interface), edges showing where each entity is defined, referenced by other entities, and used across files. Serves the frontend Graph view.

## Ownership
- `graph_builder.py` — `build_repo_graph(repo_name)` (Qdrant load path), `build_repo_graph_from_chunks(repo_name, chunks)` (in-memory path used by the orchestrator), `_build_graph_from_chunks` (shared core), `_load_repo_chunks`, reference-edge detection

## Local Contracts
- Chunk source is either Qdrant `scroll` (`build_repo_graph`, same `repo` payload filter pattern as retrieval BM25) or the in-memory `CodeChunk` list from the chunker (`build_repo_graph_from_chunks`); both feed the same `_build_graph_from_chunks` core
- Only `chunk_source == "ast"` chunks with a symbol (len >= 2) become entity nodes; deduped by `(file, symbol)`
- JS/TS arrow-function / function-expression components (`const X = () => …`, `export const X = function …`, class expressions) are NOT AST chunks, so they are synthesized as entities from JS/TS text chunks via `_js_component_declarations` (module-level `variable_declarator` with a function/class expression value; nested/boundary nodes skipped); an existing AST entity for the same `(file, symbol)` wins
- File nodes are created for every file in the repo (AST and text chunks) so all `defines`/`used_in` edge targets exist; edges are filtered at output to drop self-loops or references to missing node ids (this keeps d3-force from throwing on dangling links)
- Node schema: `{id, label, kind, file, language, start_line, end_line, content?}`; kinds map from `node_type` via `KIND_MAP` (`class`/`interface`/`impl`/`method`/`function`/`entity`/`file`)
- Content snippet capped at `MAX_SNIPPET_CHARS` (4000) — Qdrant chunk content is the only surviving code (source dir cleaned post-ingest)
- Edge schema: `{source, target, type}`; types: `defines` (entity → file), `uses` (entity → entity reference), `used_in` (entity → other file whose text references it)
- Reference detection parses each chunk's code with tree-sitter (`ParserManager`, per-language parser cache) and collects nodes whose type ends in `identifier` (identifier/type_identifier/field_identifier/...) plus `constant` nodes (Ruby class/module/constant references, a distinct node type in tree-sitter-ruby); a symbol is linked only when its name appears as such a reference in another chunk's code — comments/strings/docs never count
- `uses` edges are emitted from entity chunks (AST) and from JS/TS synthesized components (their text chunks pass the declared component keys as sources), so arrow-function/function-expression components get real outgoing `uses` edges; non-entity text chunks still emit `used_in` (file-level) edges only
- Not cached in-process anymore — graphs are persisted to Postgres (`repo_graphs` via `backend/state.py`) by the orchestrator at ingest time; `GET /graph` reads the DB (lazy fallback builds + persists for pre-existing repos)
- Result shape: `{repo, nodes, edges}`

## Work Guidance
- If AST `node_type` values change in `chunking/ast_config.py`, extend `KIND_MAP`
- Keep the builder pure — no DB/auth logic here; endpoints live in `backend/routers/repositories.py`, persistence in `backend/state.py`

## Verification
- Smoke test: `python -c "from symbol_graph.graph_builder import build_repo_graph_from_chunks; g = build_repo_graph_from_chunks('<repo>', chunks); print(len(g['nodes']), len(g['edges']))"`

## Child DOX Index
*None*
