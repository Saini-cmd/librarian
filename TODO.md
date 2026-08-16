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

## Evaluation system (built — see `evaluation/` + `DECISIONS.md`)

Done + deferred:

- [x] **Live e2e run — lynko (done)** — first run (`python -m evaluation.runner --repo https://github.com/Saini-cmd/lynko`) at `data/eval_reports/lynko_20260815_112355/` (S2 vs S1: R@K 1.000 vs 0.750; S4 best; faithfulness 0.948, relevance 1.000, citation accuracy 0.593). Also surfaced a fixed bug: commit-level existence check now guards a missing collection (404). **Superseded**: that report was deleted (pre-fix harness) — the current run is `lynko_20260816_133243/` (see D34).
- [x] **App resilience (done, D13)** — rerank failure now falls back to hybrid results (`reranked: False`) instead of crashing chat; reranker gained transient retry. Mirrored in eval S4.
- [x] **Context ablation (done, D14)** — `evaluation/context_ablation.py` on the lynko golden set: no policy beats baseline on quality; only ~21% token savings (`ratio 0.4 + per-file 2`). Knobs shipped OFF.
- [x] **Harness correctness pass (done, D15–D18)** — strict line overlap (AST gap chunks shared boundary lines and inflated S2/S3/S4 denominators), coverage-based judge + `Judge.sanity_check()` gate (relevance was 1.0 on every item), golden-set symbol-leakage retry+drop, report now shows mean±stdev + "Target in context".
- [x] **Re-run requests with the corrected harness (done)** — `data/eval_reports/requests_20260815_125452/`: the boundary-touch fix lifted S2 recall 0.597→0.833, S3 0.403→0.750, S4 0.708→0.917 (the "S1 beats S2" anomaly was largely that artifact); precision fell 0.19→0.12 (was over-counting gap chunks as relevant); judge sanity gate passes; new "Target in context" = 0.917.
- [x] **Citation anchoring prompt (tested, reverted — D19)** — definition-anchoring instruction + `qualified_name` in context moved Citation Accuracy 0.343→0.385 but dropped Faithfulness 0.900→0.837 on requests; reverted (grounding loss not worth the small citation gain).
- [ ] **Live e2e runs — more repos** — same command for requests/fastapi (needs infra + API spend).
- [x] **Re-run lynko on the current harness (done)** — `data/eval_reports/lynko_20260816_133243/` (N=20, K=8): S4 = Recall@K 1.000, MRR 0.975, Context Recall 1.000; generation Faithfulness 0.821, Answer Relevance 1.000, Target-in-context 0.95. Confirms the app works as intended (see DECISIONS.md D34).
- [ ] **Re-run express / requests / ripgrep on the current harness** — the existing reports predate MRR (D33); re-run for a clean 4-repo aggregate with MRR (cached golden sets + embedded data, no re-embed cost).
- [ ] **Investigate ripgrep S2 < S1** — on ripgrep, AST vector (0.545 R@K, R@1 = 0.000) trails naive (0.818); hypothesis: large Rust functions/impls produce big diluted AST chunks. Check chunk-size distribution vs requests/express and whether the token-aware AST splitter needs tuning for Rust.
- [ ] **Golden-set curation pass** — review LLM-paraphrased queries in `evaluation/datasets/*.json`; drop/rewrite queries that leak the symbol name or are unanswerable.
- [ ] **Judge discrimination test** — inject a known-bad answer to verify the judge actually penalizes it (Answer Relevance is currently 1.000 on all items).
- [ ] **RRF/hybrid tuning experiment** — S3 < S2 on lynko: test RRF `k`/candidate-pool sizes or drop lexical fusion on keyword-light repos (see D9 note in the report).
- [ ] **Context token-saving preset** — if token cost matters, enable `RAG_CONTEXT_MIN_SCORE_RATIO=0.4` + `RAG_CONTEXT_MAX_PER_FILE=2` as an opt-in preset (D14).
- [ ] **Generation metrics on S3** — compare S3 vs S4 answer quality (currently S4 only, per D3).
- [x] **PDF export of the HTML report (done, D35)** — `report.pdf`/`aggregate.pdf` rendered from the self-contained HTML via WeasyPrint; gracefully skipped if WeasyPrint/system libs are missing (never fails a run).
- [ ] **Recall curve definition** — graded recall variant (relevant-in-top-K / total-relevant) as an optional figure alongside the binary hit-rate curve (see D12).
- [ ] **Config schema validation** — type-check `--config` JSON keys instead of trusting them.

---

## Multi-user & scalability hardening (deferred — see `DECISIONS.md` D22)

**Design decision:** the app targets **public repos only** — this closes the private-repo chat-ownership leak by design; chat's global `repo_hash` lookup in `resolve_conversation_repo` (no `user_repo_exists`) is acceptable for a public-repo model. Graph/chunks/summary endpoints keep ownership checks for multi-user correctness.

Plan (in priority order):

- [x] **Batched Qdrant upsert (done — D21)** — `VectorIndexer.index` now batches upserts (~8MB payload target, 500-point cap). Verified live: ripgrep naive (≈44MB as one payload) lands in multiple `200` batches; **3556 AST chunks indexed in 8 batches** (was a single `400`). Ripgrep re-run (`--n 12`, 11 kept) done → `data/eval_reports/ripgrep_20260815_140916/`.
- [x] **Race-free DB upserts (done — D23)** — `upsert_user` / `get_or_create_indexed_repo` / `ensure_repo_indexing` / `save_repo_graph` / `save_conversation_summary` catch `IntegrityError` on insert, roll back + re-SELECT + adopt the concurrent winner. `repo_graph.repo_hash` UNIQUE (`uq_repo_graph_repo_hash`) — one graph per commit; live DBs predating the constraint need the manual `CREATE UNIQUE INDEX` (see `backend/AGENTS.md`). Verified via two-thread barrier races: pre-fix 9–20 exceptions/race, post-fix zero + zero dup rows.
- [x] **Clone-dir isolation (done — D24)** — `fetch_repo` clones into a unique per-run dir `data/repos/{name}-{uuid}` (no shared clone dir); `ingest()` returns `(files, repo_dir)`; orchestrator/eval/tests consume the returned path and clean it up. Fixes the mid-pipeline `rmtree` corruption when two ingests of the same repo run concurrently. Verified: concurrent double-ingest of `psf/requests` → two distinct dirs, same commit, both cleaned.
- [x] **Same-repo ingest lock (done — D25)** — new `backend/ingest_lock.py`: Redis `SET NX EX` keyed by commit hash (owner token, compare-and-del release, heartbeat renew, in-process fallback when Redis down). `/api/process` + `/sync` now **wait-and-reuse**: the holder runs the pipeline, a second concurrent caller streams `stage: "waiting"` until the commit is indexed (reuse) or takes over if the holder gives up. `/api/process` short-circuit now requires `status='indexed'` (a `failed`/`indexing`/`deleted` row is re-ingested/waited on instead of reused). Env: `INGEST_LOCK_*`. Verified: 21 checks — lock primitives, Redis-down fallback, ready/owned/timeout, live wait-and-reuse SSE, background-thread error path releases the lock.
- [x] **Pool sizing + thread-safe caches (done — D26)** — `DB_POOL_SIZE`/`DB_MAX_OVERFLOW` env-tunable; `_sync_run` holds no DB session across the pipeline (only a `status='indexed'` row is reused); `BM25Index` is thread-safe (per-commit build lock + bounded LRU, `BM25_CACHE_SIZE` default 16); `GET /graph` lazy rebuild serialized per commit; `_PARSERS` lock-guarded. Verified: 14 checks — pool settings, zero sessions during pipeline + failed-row re-ingest, BM25 concurrency + LRU eviction, lock identity, parser concurrency.
- [x] **Global ingest concurrency cap (done — D28)** — `GlobalIngestGate` caps concurrent pipelines across all users/commits (`INGEST_MAX_CONCURRENT` default 2; atomic Redis counter + sliding TTL + bounded-semaphore fallback). `wait_for_index` returns `owned` only holding both the per-commit lock AND a gate slot; a full cap keeps the caller `waiting`. Verified: 15 checks — slot acquire/cap/release, Redis-down fallback, wait-then-owned after a slot frees, timeout with cap busy, `_sync_run` releases its slot, live wait-and-reuse regression.
- [x] **Auth on `/api/reset` (done)** — the wipe endpoint now requires a Clerk JWT (`Depends(get_current_user)`); unauthenticated callers get 401. The frontend's `resetAll` helper is unused, so nothing breaks.
- [x] **Document chat ownership as by-design** — already noted in `backend/AGENTS.md` (D22): chat's global `repo_hash` lookup intentionally skips `user_repo_exists` (public-repos-only). Do not "fix" later by mistake.
- [x] **Scale notes (done — D27/D30/D31)** — `SCALE.md` (multi-worker uvicorn, per-worker vs shared state, Postgres connection math, concurrency knobs), `PRODUCTION.md` (managed infra/HA + `compose.prod.yml`), deployment hardening (`CORS_ORIGINS`, `/api/ready`, `THREADPOOL_SIZE`).

---

## Side tasks / housekeeping

- [ ] **Security: purge `.env.local` from git history** — `.env.local` (with a real `CLERK_SECRET_KEY`) was tracked in git history before deletion. It's gone from the working tree but still in history — `git rm --cached .env.local` + history purge/rotation if this repo ever goes public.

---

## Done (reference)

- Eval: added **MRR** (mean reciprocal rank of first relevant chunk) as a 4th retrieval metric across all tables/deltas/per-query (`R/P/MRR`)/aggregate (D33); Context Precision kept, report now states its structural `1/K` ceiling explicitly (e.g. 0.125 at K=8)
- Eval: **run progress** — CLI prints stage banners (`1/4`–`4/4`) + tqdm bars for embed batches (`embed_texts`/`embed_chunks` gained an optional `progress(done, total)` callback), retrieval queries (items × 4 setups), and generation items
- Prompts: consolidated every LLM prompt template (RAG, file summary, chat-memory rollups, node explain, eval judges, golden-set paraphrase) into root `prompts.py` (D32) — 6 consumers import from it; prompt output byte-identical (verified)
- Prompts: rewrote RAG system prompt (direct natural answers, no retrieval narration/dwelling on missing context) + trimmed node-explain prompt (dropped edge-cases/patterns/pitfalls, 500→150 words, `max_tokens` 700→350)
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
