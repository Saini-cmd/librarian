# TODO — Task Tracker

Working task list for the project. Check items off as they land; add side tasks as they come up. Symbol-graph implementation plan lives in `PLAN.md`; schema/identity reference lives in `DB_SCHEMA.md`.

---

## Symbol graph (see `PLAN.md` for the full plan)

- [ ] **Phase 0 — Safety net**: `tests/test_10_symbol_graph.py` (12-language graph assertions); graph JSON `version` field + `GET /graph` stale-rebuild.
- [ ] **Phase 1 — Symbol extraction**: fix C/C++ `function_definition`, Ruby `class`/`module`/`method`, Go `type_declaration`, Rust `impl_item`; add `qualified_name` + `parent_symbol` to `CodeChunk` (additive Qdrant payload keys); TSX parses with `tsx` grammar.
- [ ] **Phase 2 — Import edges**: new `symbol_graph/imports.py` — Go block imports + `go.mod` prefix, C# namespace→file, Java/Kotlin member-strip, Rust `pub mod`/`super::`/`self::`, C/C++ angle + `../`, Python package-root, JS/TS `tsconfig` aliases.
- [ ] **Phase 3 — Graph core rewrite**: qualified node ids, dedup by `(file, qualified_name)`, `contains` edges, `KIND_MAP` extension + method relabel, scoped reference resolution (same-scope → same-file → import-alias → unique-global, drop ambiguous), `uses` line/column, old-chunk fallback.
- [ ] **Phase 4 — Graph-side synthesis**: generalized text-chunk walker for consts/vars, TS `type`/`enum`, C/C++ structs/enums, Rust traits/enums/modules, C# enums/records/structs, Python async fns/module vars; JSX component synthesis after TSX fix.
- [ ] **Phase 5 — Frontend + integration**: colors for new kinds + `contains`; verify `SymbolGraph2DView`/`SymbolGraphView` + large-repo perf; stale-rebuild for pre-existing repos.
- [ ] **Phase 6 — DOX + verification**: AGENTS.md updates (`chunking/`, `symbol_graph/`, `ingestion/`, `vector_store/`, `tests/`); run `test_01`–`test_10`; `./dev.sh` smoke + real-repo spot checks.

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

- [ ] **Chat-memory worker not running** — the ARQ worker was stopped during the `repo_url` re-scope work; restart it (`venv/bin/arq memory.worker.WorkerSettings` or `./dev.sh`) before testing chat memory.
- [ ] **6 orphaned `long_term_memory` points** — for the real user's conversation (`222c104f`), written under the old `repo_hash`-scoped schema (`repo_url=None`). Unreachable under `repo_url` scoping; purge pending user decision.
- [ ] **`indexed_repo.status='syncing'` unused** — the enum value exists but sync never sets it (the new commit row goes `indexing` → `indexed`). Either set it during a sync for visibility or drop the value.
- [ ] **Drop legacy `repo` payload tolerance** — `chunk_from_payload` still falls back to the old `repo` payload key. Since Qdrant is clean (hash-only), this can be removed.
- [ ] **Security note** — `.env.local` (with a real `CLERK_SECRET_KEY`) was tracked in git history before deletion. It's gone from the working tree but still in history — `git rm --cached .env.local` + history purge/rotation if this repo ever goes public.
- [ ] **Chat divider shows in fresh new chat** — the sync-boundary divider renders even when there's no sync boundary (brand-new conversation). Fix to only appear when an actual sync boundary exists.
- [ ] **UI tweaks** — filter menu, sync screen, and the directory-filter button overflow (selected long path overflows the box).

---

## Done (reference)

- Per-commit identity (`repo_url` + `repo_hash`), hash-only Qdrant scoping
- Probe-first `/api/process` (global-hash skip) + `/api/repositories/{repo_hash}/updates`
- `/api/repositories/{repo_hash}/sync` — re-ingest/reuse → re-point conversations → tombstone old commits (retain cited chunks)
- SSE progress streaming for `/api/process` + `/sync` (background thread + queue; full-screen sync overlay, inline ingestion ProgressBar)
- Message `repo_hash` stamping + chat sync-boundary divider
- Citation chunk access from tombstoned commits + `CitationCard`/`SymbolGraphView` hash identifiers
- uvicorn `--reload-exclude data/* frontend/dist/*` (clone dirs no longer trigger mid-pipeline reloads)
