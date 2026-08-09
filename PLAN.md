# Symbol Graph Correctness Plan (all languages)

Working implementation plan for end-to-end graph correctness across all 12 supported languages. Supersedes the completed chat-memory plan (that feature shipped; its phases are marked done below). Task tracking lives in `TODO.md`; schema/identity reference lives in `DB_SCHEMA.md`.

---

## 1. Objective

Make the symbol graph correct and complete for every supported language — entity coverage, hierarchy, imports, and reference linking — **without breaking anything that exists today** (RAG, retrieval, chat, sync, frontend Graph view, persisted graphs, existing tests).

Investigation established the current graph is built from AST chunks only: entity nodes from `chunk_source == "ast"` chunks with `len(symbol) >= 2` deduped by `(file, symbol)`, plus JS/TS arrow-function synthesis; edges are `defines` / `uses` (global name-match) / `used_in` (cross-file) / `imports` (per-language regex + best-effort resolution).

## 2. Locked-in design decisions

| Decision | Choice |
|---|---|
| RAG corpus | **Frozen**. Fix symbol extraction only for node types *already* AST-chunked; recover richer entity types (enums, traits, structs, consts, modules, …) **graph-side only** by parsing text chunks with tree-sitter (same mechanism as `_js_component_declarations`). No new `wanted_nodes` → zero change to the embedding corpus / retrieval for any language |
| Ambiguous references | **Dropped** (precision over recall). A reference emits `uses` only when scoped resolution yields exactly one candidate (same-scope → same-file → alias-aware import → unique global). Today's link-to-all behavior is removed for new repos; old-repo fallback stays name-only |
| Graph persistence | **Unchanged**: graph JSON stays in Postgres `repo_graphs` via `backend/state.py` (no `repo_symbols` table). New `CodeChunk` fields are persisted as additive Qdrant payload keys so the Qdrant rebuild path (`build_repo_graph`) reproduces the same graph |
| Symbol field | `CodeChunk.symbol` stays the **bare name** (embed text / BM25 for working languages stays byte-identical). Qualification lives in new optional fields (`qualified_name`, `parent_symbol`), graph-only |
| Graph schema versioning | Graph JSON gains a `version` field (default 1); `GET /graph` lazily rebuilds + persists stale graphs. Frontend ignores unknown fields |
| Node identity | `sym:{file}:{qualified_name}` (bare-name fallback). Dedup by `(file, qualified_name)` — fixes overload/method collapse |
| Edge types | `defines` / `uses` / `used_in` / `imports` kept; new `contains` (entity → child) added. `uses` edges gain optional `line`/`column` |
| New kinds | `struct` / `enum` / `trait` / `module` / `const` / `type` / `component` added to `KIND_MAP`; Python/C++ methods relabeled `method`; frontend gets colors (unknown kinds already fall back to `entity`) |

## 3. Current-state gap (verified by probes)

- **Symbol extraction broken** (`chunking/ast_chunker.py:99` naive `child_by_field_name("name")`): C and C++ `function_definition` (name nested in `function_declarator`) → no symbols; Ruby wanted `{class, def}` — tree-sitter-ruby uses `method`, and `class`/`module` have no `name` field → **no Ruby entity nodes at all**; Go `type_declaration` (name in `type_spec`) → no types; Rust `impl_item` (no `name`) → no impls.
- **Dedup collapse**: `sym:{file}:{symbol}` merges overloads and same-named methods in different classes (`graph_builder.py:379-382`); Python/C++ methods mislabeled `function`.
- **`uses` is global name-only matching** (`graph_builder.py:414-449`): self-name contamination + no scope → spurious edges between same-named symbols and false `used_in` across files. Renamed imports (`import x as y`) missed. No line positions.
- **Import edges**: Go has no pattern at all; C# `using` resolves to a directory string → dead (`graph_builder.py:297`); Java/Kotlin static/member imports keep the member in the path; Rust `pub mod`/`super::`/`self::` missed; C/C++ angle-bracket project includes + `../` resolution fragile; Python absolute imports assume repo-root-relative.
- **JS/TS**: `.tsx` files parse with the `typescript` grammar (not `tsx`) → JSX components never synthesize (`ingestion/constants.py:29`); plain JS synthesis classifies every function-valued const as a "component".
- **No hierarchy**: no class→method / module→member / impl→method / file→member containment edges anywhere.

## 4. Data storage

- **Postgres**: no new table. `repo_graphs.graph_json` gains a `version` key (read/write in `backend/state.py:407-419`).
- **Qdrant `code_chunks` payload**: two additive keys — `qualified_name`, `parent_symbol` — written in `vector_store/indexer.py:49-63`, read with `.get()` defaults in `chunk_from_payload` (`vector_store/indexer.py:153-176`) so pre-existing points remain valid. Old repos without these keys degrade to today's name-only behavior.
- **`CodeChunk`** (`chunking/chunk_model.py`): two new optional fields, `qualified_name: str = ""`, `parent_symbol: str = ""`, populated only for AST chunks from the walk's ancestor chain.

## 5. Architecture

### 5a. Symbol extraction (chunker, minimal)
Replace naive name extraction with per-node-type logic; symbols stay bare names. Add `qualified_name` (file-module/class-dotted path) + `parent_symbol` from the ancestor chain. Fix TSX parser mapping. **No new `wanted_nodes`** — RAG corpus frozen.

### 5b. Graph-side synthesis (rich entities, zero corpus change)
Generalize `_js_component_declarations` (`symbol_graph/graph_builder.py:143`) into a per-language text-chunk walker that synthesizes nodes for entity types not in the AST-chunk corpus: module-level consts/vars, TS `type`/`enum`/`interface`, C/C++ structs/enums, Rust traits/enums/modules, C# enums/records/structs, Python async fns/module vars. Text chunks are already in Qdrant → rebuild path works.

### 5c. Reference resolution (scoped)
Build a per-repo symbol index (name → defs with scope = file + qualified ancestors + module). Extract references as chains (`AuthService.login()`, `self.x`, `Foo::bar`), resolve in order: same-scope → same-file → alias-aware imports (`import x as y`, `from x import y as z` via the Phase 2 import map) → unique global. Ambiguous → drop. Old chunks without new fields use today's name-only logic.

## 6. Implementation phases

### Phase 0 — Safety net (no behavior change)
- [ ] New `tests/test_10_symbol_graph.py` (follows `test_XX` scheme): synthetic-snippet graph builds for all 12 languages asserting node/edge expectations — C fns, Ruby `def`/modules, Go types, Rust impls, dedup collapse, per-language imports, TSX/JSX, name-collision noise.
- [ ] Graph JSON `version` field; `GET /graph` (`backend/routers/repositories.py:135-147`) version-check + lazy rebuild.

### Phase 1 — Fix symbol extraction (foundation)
- [ ] `chunking/ast_chunker.py`: per-node-type name extraction — C/C++ `function_definition` → `function_declarator` → `identifier`/`field_identifier`; Ruby wanted `{class, module, method}`, name from `constant`/first `identifier`; Go `type_declaration` → `type_spec` → `type_identifier`; Rust `impl_item` → synthesized symbol from target type (`User`, `User::Fly`).
- [ ] `chunking/ast_config.py`: correct wanted sets for Ruby (`method` not `def`); no new entity-producing wanted nodes (RAG freeze).
- [ ] `chunking/chunk_model.py`: `qualified_name`, `parent_symbol` optional fields.
- [ ] `vector_store/indexer.py` + `chunk_from_payload`: persist/read the new keys (additive).
- [ ] `chunking/parser_manager.py` / `ingestion/constants.py`: `.tsx` parses with the `tsx` grammar while keeping the `language` label stable.
- [ ] Verify: embed text / BM25 for working languages (Python/JS/TS/Java/Kotlin/C#) byte-identical; broken languages (C/Ruby/Go/Rust-impl) symbols go empty → real.

### Phase 2 — Import edges overhaul
- [ ] New `symbol_graph/imports.py` (per-language extraction + resolution), `graph_builder.py` delegates.
- [ ] Go: `import ( "x" )` extraction; first-party resolution via `go.mod` module-prefix mapping; else `None`.
- [ ] C#: namespace → file candidates, strip member names, `using X = Y;`.
- [ ] Java/Kotlin: strip member from static/member imports; wildcards.
- [ ] Rust: capture `pub mod`/`pub(crate) mod`; resolve `super::`/`self::`/`crate::`; strip item path to module.
- [ ] C/C++: angle-bracket project includes; root-relative `../` resolution.
- [ ] Python: resolve absolute imports against the detected package root (not always repo root).
- [ ] JS/TS: `tsconfig` `paths`/`baseUrl` aliases; bare specifiers stay `None`.
- [ ] `imports` stays file→file (edge schema unchanged); covered by test_10.

### Phase 3 — Graph core rewrite
- [ ] Qualified node ids `sym:{file}:{qualified_name}`; node fields `name`, `qualified_name`, `parent`; `label` stays display name.
- [ ] Dedup by `(file, qualified_name)`.
- [ ] New `contains` edge type from parent chains (class→method, module→member, impl→method, file→top-level).
- [ ] `KIND_MAP` extension + Python/C++ method relabeling.
- [ ] Scoped reference resolution (per 5c): symbol index, chain-aware reference extraction, same-scope → same-file → import-alias → unique-global, drop ambiguous; `uses` gain `line`/`column`; `used_in` derived from cross-file `uses`.
- [ ] Old-chunk fallback path preserved (name-only) — old repos still build identically.

### Phase 4 — Graph-side synthesis (rich entities)
- [ ] Generalize `_js_component_declarations` → per-language text-chunk walker (consts, TS `type`/`enum`, C/C++ structs/enums, Rust traits/enums/modules, C# enums/records/structs, Python async fns/module vars).
- [ ] TSX JSX components synthesize (depends on Phase 1); React components vs plain function consts distinguished (`component` vs `function`).

### Phase 5 — Frontend + integration
- [ ] `frontend/src/theme/index.js` + `design-system.css`: colors for new kinds and `contains` (unknown kinds/edges already fall back).
- [ ] Verify `SymbolGraph2DView` / `SymbolGraphView` handle deeper ids, new kinds, `contains`, large-repo layout perf.
- [ ] `GET /graph` stale-rebuild confirmed end-to-end for pre-existing repos.

### Phase 6 — Docs + verification (DOX pass)
- [ ] Update AGENTS.md: `chunking/` (qualified fields, no-new-wanted-nodes), `symbol_graph/` (new node/edge schema, kinds, version), `orchestration/`, `ingestion/` (tsx mapping), `vector_store/` (payload keys), `tests/` (test_10).
- [ ] Refresh `TODO.md` with remaining side tasks.
- [ ] Run: `test_01`…`test_09` + new `test_10`; `./dev.sh` smoke; Graph view render + chat RAG on an existing repo; one real repo per major language.

## 7. Expected impact

- **Graph quality**: entity nodes for all 12 languages (incl. C/Ruby/Go/Rust which are effectively empty today); no collapsed same-name symbols; real hierarchy via `contains`; precise scoped references (no cross-symbol noise); working import edges for Go/C#/Rust/C/C++.
- **RAG / retrieval**: unchanged — corpus frozen, `symbol` values unchanged for working languages, embed text / BM25 byte-identical.
- **Frontend**: additive — unknown kinds/edges already render via fallback colors; new colors are polish.
- **Persistence**: backward compatible — old graphs render, old chunks rebuild via name-only fallback, new chunks carry the richer fields.

## 8. Out of scope

- Adding new entity types to the RAG embedding corpus (deliberate — RAG freeze).
- Symbol-level `imports` edges (entity → entity across files) — import graph stays file→file.
- Cross-repo symbol resolution / monorepo-wide graphs.
- LLM-assisted reference disambiguation.
