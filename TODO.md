# TODO — Task Tracker

Working task list for the project. Check items off as they land; add side tasks as they come up. Symbol-graph implementation plan lives in `PLAN.md`; schema/identity reference lives in `DB_SCHEMA.md`.

---

## Symbol graph (see `PLAN.md` for the full plan)

- [x] **Phase 0 — Safety net (done, verified)**: `tests/test_10_symbol_graph.py` (87 checks green across 12 languages); graph JSON `version` field + `GET /graph` stale-rebuild.
- [x] **Phase 1 — Symbol extraction (done, verified)**: `node_name()` per-node-type extraction (C/C++ fns, Ruby class/module/method, Go types, Rust impl `User`/`User::Fly`); Ruby wanted `{class, module, method}`; `qualified_name` + `parent_symbol` on `CodeChunk` (additive Qdrant payload keys); TSX parses with `tsx` grammar (label stays `typescript`); `KIND_MAP` + `method`/`module`. test_10 at 92 checks.
- [x] **Phase 2 — Import edges (done, verified)**: new `symbol_graph/imports.py` — Go block imports + package-dir match, C# namespace→file, Java/Kotlin member-strip, Rust `pub mod`/`super::`/`self::`, C/C++ angle + `../`, Python package-root, JS/TS `tsconfig` aliases. test_10 at 99 checks (22 import cases + alias end-to-end).
- [x] **Phase 3 — Graph core rewrite (done, verified)**: qualified node ids + `name`/`qualified_name`/`parent`; dedup by `(file, qualified_name)`; `contains` edges (file→top-level, parent→child); method relabel under class-like parents; scoped reference resolution (chain-aware, same-scope→same-file→import→unique-global, ambiguous dropped, `uses` line/column). test_10 at 112 checks.
- [x] **Phase 4 — Graph-side synthesis (done, verified)**: generalized text-chunk walker (`symbol_graph/synthesis.py`) — consts/vars, TS `type`/`enum`, C/C++ structs/enums, Rust traits/enums/modules, C# enums/records/structs, Java enums/records, Go consts/vars, C++ namespaces; `.tsx` parsed with tsx grammar; JS/TS component vs function vs const; per-entity `uses` from own content. test_10 at 114 checks.
- [x] **Phase 5 — Frontend + integration (done, verified)**: colors for new kinds + `contains` in `theme/index.js` + `design-system.css` (all palettes); `npm run build` green.
- [x] **Phase 6 — Docs + targeted verification (done)**: AGENTS.md pass across phases; test_10 at 114 checks; app imports + frontend build.
- [x] **Graph visuals P1/P2/P3 (done, verified)**: `onlyRenderVisibleElements` + adjacency-memo selection + redundant-edge pruning (P1); `contains`+`imports` structural layout (P2); nested file-group nodes with two-pass ELK per-file columns (P3); file-group handles so `imports`/`used_in` edges render. `npm run build` green.

---

## Deferred symbol-graph verification (needs infra + API spend)

- [ ] **Full live verification** — infra up (`docker compose up -d`), then run `tests/test_01`…`test_09` + `test_10`; `./dev.sh` smoke; Graph view render (new kinds/`contains` colors) + chat RAG on an existing repo.
- [ ] **Real-repo spot checks** — ingest one repo per major language (Python, JS/TS, C/C++, Rust, Go, C#, Ruby, Java, Kotlin) and eyeball the graph: entity coverage, containment, imports, scoped refs.
- [ ] **`GET /graph` stale-rebuild e2e** — confirm a pre-existing persisted graph rebuilds when its `version` is below `GRAPH_VERSION`.

---

## Chat memory (shipped — see git history)

- [x] **Phase 2 — Read path**: `_to_langchain` assistant role; `prompt_builder` multi-turn + memory injection; `answer_generator` threading; both chat endpoints assemble history + long-term memory (`build_memory_context`) and enqueue background jobs after persisting the assistant message.
- [x] **Phase 3 — Write path / workers**: `rollup_session_summary` (gated, merged, watermark-advanced, shared `SUMMARIZE_*` OpenRouter config); `summarization/llm_config.py` + `file_summarizer.py` on `ling-3.0-flash`; `redis:7` service; ARQ worker verified live.
- [x] **Phase 4 — Cleanup/config/tests/DOX**: conversation delete purges memory; reset wipes `long_term_memory`; `.env.example` `MEMORY_*`/`SUMMARIZE_*`/`REDIS_URL`; `dev.sh` starts the ARQ worker + Redis health wait; `tests/test_09_memory.py`; `FileSummarizer` quality spot-check passed.

---

## Remaining sync-feature work

- [ ] **Repos list UI** — `GET /api/repositories` already returns one `RepoOut` per repo (latest commit, `repo_hash`, `status`, counts) but the frontend never renders it; repos surface only via conversations + the header Sync button. Add a small repos panel (per-repo `updates_available` + Sync + status). Optionally fold the `updates` probe into the list response instead of the separate endpoint.
- [ ] **Jump-to-current-version for citations** — after sync, old cited chunks still open fine (retained), but a "jump to the current version" of a changed file isn't implemented. Best-effort lookup by `(repo_hash, file_path)` + `symbol`, line-overlap fallback since lines shift on sync. No snippet stored (a full `/api/reset` wipes cited chunk content too).
- [ ] **Tombstone purge** — `status='deleted'` rows + their retained chunks only get cleaned up when a conversation is deleted (citations cascade). Purge tombstones + retained chunks when the citations' messages are deleted.
- [ ] **Smoke tests review** — run/update `tests/test_0*.py` against the new model. `test_05_retrieval` was updated for `repo_url`; the rest haven't been run end-to-end (full-pipeline tests that cost API calls).
- [ ] **Legacy message backfill (optional)** — the pre-feature `messages` rows have `repo_hash = NULL`. Backfill from the `citation` table (assistant messages: own citation rows; user messages: inherit the next assistant message's hash). Data-cleanup nicety only — no effect on the divider or behavior.

---

## Side tasks / housekeeping

- [ ] **Security: purge `.env.local` from git history** — `.env.local` (with a real `CLERK_SECRET_KEY`) was tracked in git history before deletion. It's gone from the working tree but still in history — `git rm --cached .env.local` + history purge/rotation if this repo ever goes public.

---

## Done (reference)

- Housekeeping: purged 6 orphaned `long_term_memory` points (old `repo_hash`-scoped schema, `repo_url=None`); confirmed chat-memory ARQ worker runs; dropped unused `indexed_repo.status` values (`pending`, `syncing`) from the documented set (real set: `indexing | indexed | failed | deleted`); removed legacy `repo` payload-key fallback in `chunk_from_payload`; fixed sync-boundary divider rendering in brand-new chats (was showing with no boundary); graph filter closes on repo change, dir-filter select truncates + tooltips, sync overlay shows the repo name
- Graph: removed the `contains` edge type end-to-end (backend no longer emits it; `GRAPH_VERSION` bumped to 2; frontend theme/layout/legend updated) — containment is shown structurally by the nested file-group nodes
- Graph: removed the `defines` edge type end-to-end (backend no longer emits it; `GRAPH_VERSION` bumped to 3; frontend theme/legend updated, `isRenderableEdge` gone) — file membership is shown by the nesting; final edge set is `uses` / `used_in` / `imports`
- Summarization: retry-with-backoff per file (`SUMMARIZE_MAX_ATTEMPTS`/`SUMMARIZE_CONCURRENCY`) + real error logged (`exc_info`)
- Per-commit identity (`repo_url` + `repo_hash`), hash-only Qdrant scoping
- Probe-first `/api/process` (global-hash skip) + `/api/repositories/{repo_hash}/updates`
- `/api/repositories/{repo_hash}/sync` — re-ingest/reuse → re-point conversations → tombstone old commits (retain cited chunks)
- SSE progress streaming for `/api/process` + `/sync` (background thread + queue; full-screen sync overlay, inline ingestion ProgressBar)
- Message `repo_hash` stamping + chat sync-boundary divider
- Citation chunk access from tombstoned commits + `CitationCard`/`SymbolGraphView` hash identifiers
- uvicorn `--reload-exclude data/* frontend/dist/*` (clone dirs no longer trigger mid-pipeline reloads)
