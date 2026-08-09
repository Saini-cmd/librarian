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
| Edge types | `uses` / `used_in` / `imports`. `uses` edges gain optional `line`/`column`. File membership and containment are **not** edge types — the frontend renders them structurally by nesting each file's entities inside the file node |
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

### Phase 0 — Safety net (done, verified)
- [x] New `tests/test_10_symbol_graph.py` (follows `test_XX` scheme): synthetic-snippet graph builds for all 12 languages asserting node/edge expectations — C fns, Ruby `def`/modules, Go types, Rust impls, dedup collapse, per-language imports, TSX/JSX, name-collision noise. Verified: 87 checks green (`python tests/test_10_symbol_graph.py`).
- [x] Graph JSON `version` field; `GET /graph` (`backend/routers/repositories.py:135-147`) version-check + lazy rebuild.

### Phase 1 — Fix symbol extraction (done, verified)
- [x] `chunking/ast_chunker.py`: unified `node_name()` per-node-type name extraction — C/C++ `function_definition` → `function_declarator` → identifier; Ruby `class`/`module` → constant, `method` → first identifier; Go `type_declaration` → `type_spec`; Rust `impl_item` → `User` / `User::Fly`; named-ancestor chain threaded through `collect_tree_nodes` → `qualified_name` (dotted) + `parent_symbol` (nearest named ancestor). Symbols stay bare names.
- [x] `chunking/ast_config.py`: Ruby wanted set `{class, module, method}` (was `{class, def}` — tree-sitter-ruby's real node type is `method`). No new wanted nodes elsewhere (RAG freeze holds).
- [x] `chunking/chunk_model.py`: `qualified_name`, `parent_symbol` optional fields (graph-only; not in embed text).
- [x] `vector_store/indexer.py` + `chunk_from_payload`: persist/read the new keys (additive, `.get` defaults → old points valid).
- [x] TSX: `.tsx` files parse with the `tsx` grammar via an extension override in `ast_chunker` (parser_language), keeping the `language` label `typescript` stable.
- [x] `KIND_MAP`: added `method` + `module` (Ruby node types).
- [x] Verified: `python tests/test_10_symbol_graph.py` — 92 checks green; working languages (Python/JS/TS/Java/Kotlin/C#) byte-identical (symbol/entity sets unchanged, no parent-chain pollution); C/C++/Ruby/Go/Rust-impl symbols empty → real; payload round-trip + old-payload compat confirmed.

### Phase 2 — Import edges (done, verified)
- [x] New `symbol_graph/imports.py` (extraction + resolution); `graph_builder.py` delegates (`extract_import_refs`/`resolve_import`/`load_ts_aliases`).
- [x] Go: block + single-line extraction; first-party resolution via package-dir suffix match against `.go` files (no `go.mod` needed); externals → `None`.
- [x] C#: namespace → file (progressive dir + file candidates, `using X = Y;` alias target); externals → `None`.
- [x] Java/Kotlin: static/member imports progressively stripped (`a.b.C.M` → `a/b/C`), wildcards handled.
- [x] Rust: `pub mod`/`pub(crate) mod` captured; `super::`/`self::`/`crate::` resolved; item path stripped to module; `std`/`core` → `None`.
- [x] C/C++: quoted + angle project includes; source-dir/ancestor-dir/root/src-root candidates fix `../` and angle includes.
- [x] Python: absolute imports resolved against package roots (nearest `__init__.py` ancestors) + repo root (fixes `src/` layouts).
- [x] JS/TS: tsconfig `paths`/`baseUrl` aliases loaded from the `tsconfig.json`/`jsconfig.json` chunk (`@/...` → file); bare specifiers stay `None`.
- [x] `imports` stays file→file (edge schema unchanged); verified in test_10 (all 22 import cases + tsconfig alias end-to-end pass).

### Phase 3 — Graph core rewrite (done, verified)
- [x] Qualified node ids `sym:{file}:{qualified_name}` (bare-name fallback for old chunks); node fields `name`, `qualified_name`, `parent`; `label` stays display name.
- [x] Dedup by `(file, qualified_name)` — same-name methods in different classes stay distinct (tested).
- [x] New `contains` edge type: file → top-level entities, parent entity → child (from qualified chains); `defines` unchanged.
- [x] `KIND_MAP` + method relabel: functions nested under a class-like parent (`class`/`interface`/`impl`) become `method`.
- [x] Scoped reference resolution: chain-aware extraction (`AuthService.login()`), resolve same-scope → same-file → imported-module (reuses import map) → unique-global; ambiguous dropped; `uses` edges gain `line`/`column`; `used_in` emitted for cross-file refs.
- [x] Old-chunk fallback: no `qualified_name`/`parent` → bare-name ids + name-only resolution (old Qdrant payloads still build).
- [x] Verified: test_10 at 112 checks (noise-elimination, dedup, contains, method relabel, chain resolution, ambiguous-drop, node schema).

### Phase 4 — Graph-side synthesis (done, verified)
- [x] Generalized text-chunk walker in `symbol_graph/synthesis.py`: module-level consts/vars (Python, Ruby, Kotlin, JS/TS), TS `type`/`enum`, C/C++ structs/enums/unions/typedefs + C++ namespaces, Rust traits (+ methods)/enums/types/consts/statics/modules, C# enums/records/structs/delegates, Java enums/records, Go consts/vars — all mined from text chunks, **zero RAG-corpus change**.
- [x] Synthesized containers (trait/module/namespace) qualify nested declarations (`Fly.fly`, `parent="Fly"`), feeding `contains`.
- [x] TSX: `.tsx` chunks (language `typescript`) parsed with the JSX-aware `tsx` grammar in synthesis + reference detection (extension-based).
- [x] JS/TS components distinguished: PascalCase/JSX arrow/function consts → `component`; lowercase → `function`; non-function consts → `const`; class expressions → `class`.
- [x] Each synthesized entity emits `uses` from its OWN declaration content (not the whole text chunk) — avoids N² const noise.
- [x] Verified: test_10 at 114 checks (rich-entity coverage per language, component vs function, .tsx JSX, const kinds); sanity builds across all 12 languages show enums/structs/types/consts/traits/records present; component `uses` + imports edges correct.

### Phase 5 — Frontend + integration (done, verified)
- [x] `frontend/src/theme/index.js` + `design-system.css`: colors for the new kinds (`struct`/`enum`/`trait`/`module`/`type`/`const`/`var`/`record`/`union`/`component`) and the `contains` edge, in all palettes (`:root`/brutalist+glass dark, apple-glass light, clay light); JS fallbacks in sync.
- [x] Verified `SymbolGraph2DView`/`SymbolGraphView`: node-kind color lookup falls back to `entity`, edge color to `fallback`; the ELK layout still uses `defines`+`imports` as structural edges (adding `contains` would create file-entity cycles) while `contains`/`uses`/`used_in` render on top; kind filter menu derives from loaded kinds automatically. Frontend builds clean (`npm run build`).
- [x] `GET /graph` stale-rebuild: version-check logic landed in Phase 0 (`graph.get("version", 0) < GRAPH_VERSION`) and the version field is asserted in test_10; live end-to-end against Postgres/Qdrant needs infra + a real repo (deferred — see TODO.md).

### Phase 6 — Docs + verification (done, targeted)
- [x] AGENTS.md updated across phases: `chunking/` (Phase 1), `symbol_graph/` (Phases 0-4), `vector_store/` (Phase 1), `tests/` (Phase 0), root row for `symbol_graph/` (Phase 5); `orchestration/` + `ingestion/` needed no changes (flow/extension mapping unchanged).
- [x] `TODO.md` refreshed (phases done + deferred live-verification items added).
- [x] Targeted verification: `tests/test_10_symbol_graph.py` (114 checks), Python syntax + app imports, frontend `npm run build`.
- [ ] Full `test_01`…`test_09` + `./dev.sh` smoke + Graph view render + chat RAG on an existing repo + one real repo per major language — requires infra up + network + OpenRouter API spend; **deferred** (tracked in TODO.md).

## 7. Expected impact

- **Graph quality**: entity nodes for all 12 languages (incl. C/Ruby/Go/Rust which are effectively empty today); no collapsed same-name symbols; precise scoped references (no cross-symbol noise); working import edges for Go/C#/Rust/C/C++. Hierarchy is conveyed structurally by the frontend (entities nested inside file nodes)
- **RAG / retrieval**: unchanged — corpus frozen, `symbol` values unchanged for working languages, embed text / BM25 byte-identical.
- **Frontend**: additive — unknown kinds/edges already render via fallback colors; new colors are polish.
- **Persistence**: backward compatible — old graphs render, old chunks rebuild via name-only fallback, new chunks carry the richer fields.

## 8. Out of scope

- Adding new entity types to the RAG embedding corpus (deliberate — RAG freeze).
- Symbol-level `imports` edges (entity → entity across files) — import graph stays file→file.
- Cross-repo symbol resolution / monorepo-wide graphs.
- LLM-assisted reference disambiguation.
