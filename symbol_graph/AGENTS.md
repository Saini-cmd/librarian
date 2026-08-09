# symbol_graph/

## Purpose
Builds a symbol graph for an indexed repo from its AST chunks: nodes for files and entities (class/function/method/interface), edges showing where each entity is defined, referenced by other entities, and used across files. Serves the frontend Graph view.

## Ownership
- `graph_builder.py` — `build_repo_graph(repo_hash, repo_label=None)` (Qdrant load path, scoped to a commit), `build_repo_graph_from_chunks(repo_label, chunks)` (in-memory path used by the orchestrator), `_build_graph_from_chunks` (shared core), `_load_repo_chunks`, scoped reference detection, `GRAPH_VERSION` (graph schema version, emitted in the result)
- `imports.py` — per-language import extraction (`extract_import_refs`) + best-effort resolution to repo files (`resolve_import`, tsconfig `paths` aliases via `load_ts_aliases`); `graph_builder` delegates here for `imports` edges
- `synthesis.py` — graph-side entity synthesis (`synthesize_entities`) from text chunks (RAG-freeze): module-level consts/vars, TS `type`/`enum`, C/C++ structs/enums/unions/typedefs + namespaces, Rust traits/enums/types/consts/statics/modules (+ trait methods), C# enums/records/structs/delegates, Java enums/records, Go consts/vars, JS/TS components vs functions vs consts; `.tsx` parsed with the JSX-aware `tsx` grammar via `extension`

## Local Contracts
- Chunk source is either Qdrant `scroll` (`build_repo_graph`, same `repo_hash` payload filter pattern as retrieval BM25) or the in-memory `CodeChunk` list from the chunker (`build_repo_graph_from_chunks`); both feed the same `_build_graph_from_chunks` core
- `repo_label` is display-only (the graph JSON `repo` field); scoping is by `repo_hash` alone (globally unique)
- Only `chunk_source == "ast"` chunks with a symbol (len >= 2) become entity nodes; deduped by `(file, qualified_name)` (chunks without `qualified_name` — old payloads — fall back to the bare symbol)
- **RAG-freeze synthesis**: entity types NOT AST-chunked (enums, structs, type aliases, consts/vars, traits, modules, records, JS/TS components) are synthesized graph-side from text chunks via `synthesis.synthesize_entities` (parses chunk content; `MIN_SYMBOL_LEN`-filtered, deduped against AST entities — AST wins). Containers (trait/module/namespace) qualify nested declarations (`Fly.fly`, `parent="Fly"`). `.tsx` chunks (`language="typescript"`, `extension=".tsx"`) parse with the JSX-aware `tsx` grammar. JS/TS arrow/function consts → `component` (PascalCase/JSX) or `function`; non-function consts → `const`
- Node id is `sym:{file}:{qualified_name}`; node schema: `{id, label, name, qualified_name, parent, kind, node_type, file, language, start_line, end_line, content?}` — `label`/`name` are the bare symbol, `qualified_name` the dotted chain (e.g. `Walker.walk`), `parent` the nearest named ancestor (e.g. `Walker`, `""` for top-level). Kinds map from `node_type` via `KIND_MAP` (`class`/`interface`/`impl`/`method`/`function`/`module`/`entity`/`file`) plus synthesized kinds (`struct`/`enum`/`trait`/`type`/`const`/`var`/`record`/`union`/`component`); a `function_definition`/`function_item` nested under a class-like parent node is relabeled `method`
- File nodes are created for every file in the repo (AST and text chunks) so all `used_in` edge targets exist; edges are filtered at output to drop self-loops or references to missing node ids (this keeps d3-force from throwing on dangling links)
- Content snippet capped at `MAX_SNIPPET_CHARS` (4000) — Qdrant chunk content is the only surviving code (source dir cleaned post-ingest)
- Edge schema: `{source, target, type}` (plus optional `line`/`column` on `uses`); types: `uses` (entity → entity reference), `used_in` (entity → other file whose text references it), `imports` (file → file). File membership and containment are **not** edge types — the frontend renders them structurally by nesting each file's entities inside the file node
- **Scoped reference resolution**: each chunk is parsed with tree-sitter and every identifier (plus Ruby `constant`) is collected; member-access fields get their object chain (`AuthService.login()`). A reference resolves through a cascade — same-scope (same file + same parent) → same-file unique → imported module (files this file imports) → unique global — and **ambiguous references are dropped** (precision over recall; no link-to-all). `uses` edges carry the first reference's `line`/`column`; `used_in` is emitted for cross-file references
- `imports` edges: per-language extraction + best-effort resolution in `imports.py` — Go block/single imports resolved via package-dir match; C# namespace → file (dir + file candidates); Java/Kotlin static/member imports progressively stripped; Rust `pub mod`/`super::`/`self::`/`crate::`; C/C++ quoted + angle project includes via source-dir/root/src-root candidates; Python absolute imports against package roots (`__init__.py` boundaries) + repo root; JS/TS tsconfig `paths` aliases (`load_ts_aliases` from the `tsconfig.json`/`jsconfig.json` chunk). Unresolvable refs (external packages, stdlib) → `None` → no edge
- `uses` edges are emitted from AST entity chunks and from synthesized entities — each synthesized entity scans **its own declaration content** for references (a component's JSX/body), so it gets real outgoing `uses` edges without the whole text chunk's noise; non-entity text chunks still emit `used_in` (file-level) edges only
- Not cached in-process anymore — graphs are persisted to Postgres (`repo_graphs` via `backend/state.py`) by the orchestrator at ingest time; `GET /graph` reads the DB (lazy fallback builds + persists for pre-existing repos, and rebuilds stored graphs whose `version` is below `GRAPH_VERSION`)
- Result shape: `{repo, version, nodes, edges}` — `version` is the graph schema version (`GRAPH_VERSION` in `graph_builder.py`); bump it when the graph JSON shape changes so `GET /graph` lazily rebuilds stale persisted graphs

## Work Guidance
- If AST `node_type` values change in `chunking/ast_config.py`, extend `KIND_MAP`
- Keep the builder pure — no DB/auth logic here; endpoints live in `backend/routers/repositories.py`, persistence in `backend/state.py`

## Verification
- Smoke test: `python -c "from symbol_graph.graph_builder import build_repo_graph_from_chunks; g = build_repo_graph_from_chunks('<repo>', chunks); print(len(g['nodes']), len(g['edges']))"`

## Child DOX Index
*None*
