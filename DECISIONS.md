# DECISIONS — Key Decisions Log

Running log of significant design decisions made while building the evaluation system. Each entry records the date, the decision, the rationale, and the alternatives rejected. `evaluation/AGENTS.md` requires keeping this current.

---

## Evaluation system

### D1 — Span-based ground truth
- **Date**: 2026-08-15
- **Decision**: Golden-set ground truth is defined at the `(file, line range)` level (a `GoldenItem` points at a code span), not at the chunk-id level.
- **Rationale**: The same golden set must evaluate both chunking strategies (S1 naive token chunks vs S2 AST chunks), which have different boundaries. A relevance test of "retrieved chunk overlaps the ground-truth span" works across both.
- **Alternatives rejected**: chunk-id-based ground truth (breaks when chunk boundaries differ between strategies); pure entity-name matching (fragile, name leakage).

### D2 — Synthetic golden set from the symbol graph / AST chunks
- **Date**: 2026-08-15
- **Decision**: Golden sets are generated per repo: sample ~20 named AST entities (functions/classes/methods carrying `qualified_name`), then have DeepSeek paraphrase each entity's code into a natural developer question (symbol name hidden). Cached as committed JSON in `evaluation/datasets/<repo>_golden.json`.
- **Rationale**: Reproducible, zero manual labeling, works on any repo.
- **Alternatives rejected**: fully manual golden sets (laborious, repo-specific); real user queries only (not available in volume).

### D3 — Generation metrics on S4 only
- **Date**: 2026-08-15
- **Decision**: Faithfulness, Answer Relevance, and Citation Accuracy are computed only for the production setup (S4, hybrid + rerank).
- **Rationale**: Retrieval metrics (Context Recall/Precision, Recall@K) already measure the S1–S3 difference; generation judging costs LLM calls per query per setup, so limiting to S4 keeps cost reasonable.
- **Alternatives rejected**: judging all setups (≈4× judge cost).

### D4 — DeepSeek as the LLM judge
- **Date**: 2026-08-15
- **Decision**: Faithfulness and Answer Relevance use the existing DeepSeek config (`DEEPSEEK_*`, `rag/llm_client.py`) as judge.
- **Rationale**: No new API keys, consistent with the answer generator.
- **Alternatives rejected**: a frontier model via OpenRouter (extra cost/key).

### D5 — Deterministic span-overlap Citation Accuracy — REMOVED from the harness
- **Date**: 2026-08-15 (removed 2026-08-15)
- **Decision (removed)**: Citation Accuracy (a citation is accurate iff its span overlaps the golden span) was dropped from the evaluation entirely, along with the report's "Sample answer" section. The eval now scores six metrics; chat citations remain an app feature but are not evaluated.
- **Rationale for removal**: The strict span-overlap score (0.34–0.59 across repos) was dominated by legitimate citations to supporting/usage code, and a prompt-level fix (D19) traded grounding for a small citation gain before being reverted. Rather than ship a misleading metric, citation evaluation was removed. A fairer LLM-judge attribution check was considered but is not currently planned.
- **Alternatives rejected**: LLM-judged attribution as the headline metric (cost, non-determinism); keeping the deterministic metric (misleading); post-hoc citation re-anchoring (fragile, tested and reverted as D19).

### D6 — Isolated evaluation collections
- **Date**: 2026-08-15
- **Decision**: Eval ingests a repo into two dedicated Qdrant collections — `code_chunks_eval_naive` and `code_chunks_eval_ast` — scoped per-repo by `repo_hash`.
- **Rationale**: Never pollutes the production `code_chunks` collection; repos coexist in the same eval collections via hash scoping; apples-to-apples A/B of chunking.
- **Alternatives rejected**: reusing the live `code_chunks` collection (mixing eval artifacts into production).

### D7 — URL-driven, repeatable harness
- **Date**: 2026-08-15
- **Decision**: The runner is invoked with one or more repo URLs (`--repo <url>`), works on any repo, caches golden sets, ingests incrementally (only missing chunks embedded), and writes timestamped reports under `data/eval_reports/<repo>_<ts>/`.
- **Rationale**: It is a reusable regression tool, not a one-off script; per-repo isolation plus cached artifacts make re-runs cheap and reproducible.
- **Alternatives rejected**: fixed hard-coded repo list in a script.

### D8 — Professional HTML report + static matplotlib figures
- **Date**: 2026-08-15
- **Decision**: Primary deliverable is a self-contained HTML report (inline CSS, embedded figures) styled like an academic paper, plus machine-readable JSON and copy-pasteable Markdown. Figures are static journal-style matplotlib (grouped bars, component-delta chart, Recall@K curve, aggregate multi-repo chart).
- **Rationale**: The user posts evaluation results publicly; academic, print-quality presentation is the goal. HTML is shareable/emailable and prints to PDF from a browser.
- **Alternatives rejected**: interactive plotly (less paper-like); PDF as primary (extra dependency, build complexity — deferred).

### D9 — All setups return the same final depth K
- **Date**: 2026-08-15
- **Decision**: Every setup (S1–S4) returns exactly `final_top_k` ranked results (default 8), and Recall@K / Context Precision are computed against that fixed K.
- **Rationale**: Comparisons across setups must be apples-to-apples at the same retrieval depth; otherwise precision and hit-rate are confounded by different list lengths.
- **Alternatives rejected**: letting each setup return its natural candidate count (unfair comparison).

### D10 — S1/S2 are pure vector baselines (no score shaping)
- **Date**: 2026-08-15
- **Decision**: S1 and S2 run pure dense vector search ranked by cosine similarity only; the production post-retrieval score boosting/dedup is applied only to S3 and S4.
- **Rationale**: The S2−S1 delta must isolate the chunking-strategy effect, and S1/S2 are deliberately "baseline" setups. S3/S4 keep production score shaping so S4 matches the real pipeline and the S4−S3 rerank delta is measured on the production path.
- **Alternatives rejected**: applying post-processing uniformly (mixes retrieval-quality effects into the chunking comparison).

### D11 — Commit-level existence for incremental eval ingestion
- **Date**: 2026-08-15
- **Decision**: Eval ingestion skips embedding an entire commit when the target eval collection already holds any point for that `repo_hash` (Qdrant `count`), rather than skipping per-chunk.
- **Rationale**: Chunk ids are UUIDs regenerated every run, so per-chunk existence checks never hit — they would re-embed the whole repo on every run. Commit-level checks make re-runs cheap while remaining correct.
- **Alternatives rejected**: per-chunk `exists()` skip (broken with non-deterministic chunk ids); deterministic chunk ids (larger cross-cutting change to production chunking).

### D12 — Recall@K headline is binary hit rate; curve is the same metric vs K
- **Date**: 2026-08-15
- **Decision**: The headline Recall@K is the binary hit rate (1 if a relevant chunk is in the top-K, averaged over golden items), and the Recall@K curve plots that same hit rate for K = 1..K.
- **Rationale**: Matches the user's definition ("how often is the ground-truth entity present in the top K"), keeps the report internally consistent, and avoids mixing graded and binary definitions in a public-facing report.
- **Alternatives rejected**: a graded recall curve (relevant-in-top-K / total-relevant) — more informative but inconsistent with the headline metric.

### D13 — Rerank failure degrades to hybrid (S3), never crashes chat
- **Date**: 2026-08-15
- **Decision**: `RetrievalPipeline.retrieve` (and the eval's S4 mirror) wrap the rerank call in `try/except`; on failure they log a warning (`exc_info`) and fall back to the post-processed hybrid candidates (adjusted-score order, sliced to `final_top_k`), tagging each result `"reranked": False`. The reranker also gained transient retry w/ backoff (429/5xx) so blips don't trigger the fallback.
- **Rationale**: The app (S4) was "rerank or nothing" — a rerank outage raised out of `retrieve()` and broke the chat endpoint. Degrading to hybrid keeps chat alive at a known (worse) quality level instead of failing.
- **Alternatives rejected**: vector/S2 fallback (best degraded ranking on lynko but more code); no fallback (chat breaks on outage).

### D14 — Context curation stays OFF until a policy is validated
- **Date**: 2026-08-15
- **Decision**: `ContextBuilder` gains optional knobs (`max_per_file`, `min_score`, `min_score_ratio`, plus `RAG_CONTEXT_*` env vars) but all default to off — app behavior is unchanged. An ablation run (`evaluation/context_ablation.py`) on the lynko golden set tested 4 policies.
- **Rationale**: On lynko, no policy improved faithfulness/citation/relevance over the baseline — the only measurable gain was ~21% fewer context tokens (`ratio 0.4 + per-file 2`: faith 0.938 ≈ baseline 0.932, cite 0.664 ≈ 0.688, 434→343 tokens, relevant chunk survived 100% in all policies). The "noise hurts answers" hypothesis is not strongly supported here (baseline faithfulness was already 0.93). Given that, changing default behavior without a quality win is not justified; the knobs remain available as a token-saving preset.
- **Alternatives rejected**: shipping a conservative default immediately (would change behavior without a demonstrated quality benefit).

### D15 — Strict line overlap for relevance (boundary-touch fix)
- **Date**: 2026-08-15
- **Decision**: `chunk_relevant` uses strict overlap (`start < item.end and end > item.start`), so a chunk that merely touches a span boundary line is NOT relevant.
- **Rationale**: The AST chunker emits gap-filler text chunks that share the entity's first/last line (e.g. entity `36-45` with gaps `1-36` and `45-116`). Inclusive-overlap counted all three as relevant, inflating the S2/S3/S4 denominators (requests-1 showed 3 "relevant" chunks for a 10-line function) and distorting recall/precision. The fix measures "did you retrieve the entity's code", not "did you retrieve a chunk sharing a boundary line".
- **Alternatives rejected**: excluding text-source chunks from relevance (breaks the naive collection comparison); per-collection logic (over-complex).

### D16 — Judge protocol v2 + sanity gate
- **Date**: 2026-08-15
- **Decision**: Answer Relevance now uses a coverage protocol (enumerate the question's requirements, score = fraction addressed) and Faithfulness is explicitly strict about unverifiable claims. Added `Judge.sanity_check()`, run once per eval, which scores a known-good vs a known-hallucinated answer and fails the run's judge if they don't differ by ≥0.3.
- **Rationale**: The old relevance judge gave 1.000 on every item across both repos — it added no information. A judge that cannot tell a good answer from a hallucination cannot validate generation metrics; the sanity gate surfaces this explicitly in the report instead of silently trusting a useless metric.
- **Alternatives rejected**: keeping the lenient judge (no information); hardcoding a penalty (gaming).

### D17 — Golden-set symbol-leakage filter
- **Date**: 2026-08-15
- **Decision**: Paraphrased queries that reveal the target symbol (or a qualified-name part, word-bounded, symbols ≥4 chars) are retried once with a forced rewrite and dropped if still leaked.
- **Rationale**: A query naming the target symbol makes retrieval trivially easy and inflates all retrieval metrics; the filter keeps the golden set hard and honest.
- **Alternatives rejected**: no filter (leakage risk); including file-stem in the leak check (too many false positives).

### D18 — Report shows variance + target-in-context
- **Date**: 2026-08-15
- **Decision**: Retrieval tables now report per-setup mean ± per-question standard deviation, and the generation section adds "Target in context" (fraction of questions whose ground-truth code survived into the LLM context).
- **Rationale**: At N=12–20 a mean alone overstates certainty (and run-to-run judge variance was ~0.02 on faithfulness). "Target in context" directly answers whether the right code reached the LLM, the strongest single signal of app quality.
- **Alternatives rejected**: confidence intervals (overkill at this N); no variance reporting (misleading).

### D19 — Citation anchoring prompt: tested and REVERTED
- **Date**: 2026-08-15
- **Decision**: Added a definition-anchoring instruction to `rag/prompt_builder.py`'s system prompt (cite each symbol's definition chunk as the primary citation) plus `qualified_name` in the context format, then measured it on the requests golden set. On one run it moved Citation Accuracy 0.343→0.385 but **dropped Faithfulness 0.900→0.837** (several items −0.1 to −0.23). **Reverted.** The system prompt and context format are back to the pre-fix state.
- **Rationale**: The trade was grounding for a small, noisy citation gain — a bad deal for a production app where faithfulness (no hallucination) matters more than citation exactness. The one clean win (requests-3: cite 0.50→1.00, faith held) shows the mechanism works for some items, but not consistently enough to justify the faithfulness regression.
- **Alternatives rejected**: keeping the change (unjustified grounding cost); a softer instruction (no second data point to tune against); the LLM-judge attribution metric as the real fix (fairer measurement, extra cost — still deferred to TODO).

### D20 — Harness findings validated: the requests "S1 beats S2" was a measurement artifact
- **Date**: 2026-08-15
- **Decision**: Recorded as a decision/rationale rather than a code rule. After the strict-overlap fix (D15), re-running requests corrected S2 recall 0.597→0.833, S3 0.403→0.750, S4 0.708→0.917; the S1>S2 anomaly was largely the boundary-touch artifact. S2 still trails S1 on Recall@K (0.833 vs 0.917) — a small, real residual, not the bug.
- **Rationale**: Confirms the harness fix (D15) produced the corrected picture and that semantic chunking helps on both repos evaluated; precision was over-reported (~0.19 → ~0.12 real) because gap chunks counted as relevant.

### D21 — Batched Qdrant upserts (ripgrep 400)
- **Date**: 2026-08-15
- **Decision**: `VectorIndexer.index` must batch upserts by estimated payload size (~8MB target, under Qdrant's 32MB request cap) with a point-count fallback, instead of one upsert for all points.
- **Rationale**: A single upsert of a content-heavy repo (ripgrep naive ≈44MB) is rejected with `400 Payload error ... larger than allowed`. Fixes both the eval ingest and production ingestion (shared code path).
- **Alternatives rejected**: raising the Qdrant request limit (server-side change, not available here); skipping large repos (unacceptable).

### D22 — App targets public repos only
- **Date**: 2026-08-15
- **Decision**: The app is limited to public repositories. Chat's global `repo_hash` retrieval in `resolve_conversation_repo` (which intentionally does NOT call `user_repo_exists`) is accepted as by-design; repo-scoped graph/chunks/summary endpoints keep ownership checks for multi-user correctness.
- **Rationale**: Closes the private-repo chat-ownership leak (any authenticated user knowing a hash could query its chunks) by making private repos unsupported rather than by adding an ownership gate to chat. Matches the intended product scope.
- **Alternatives rejected**: adding `user_repo_exists` to the chat path (ownership via conversations adds friction for the shared-public-repo model); keeping private-repo support (leak risk).

### D23 — Race-free DB upserts (multi-user Phase 1)
- **Date**: 2026-08-16
- **Decision**: The get-or-create write helpers (`upsert_user`, `get_or_create_indexed_repo`, `ensure_repo_indexing`, `save_repo_graph`, `save_conversation_summary`) catch `IntegrityError` on the insert path, roll back, re-SELECT, and adopt/merge the concurrent winner's row — instead of letting a unique/FK violation surface as a 500. `repo_graph.repo_hash` gained a **UNIQUE constraint** (`uq_repo_graph_repo_hash`, one graph per commit) so a concurrent lazy graph rebuild cannot create duplicate rows; existing live DBs need the manual `CREATE UNIQUE INDEX`.
- **Rationale**: The app is single-process today, but `upsert_user` runs on every authenticated request and concurrent first-use (two users, or the ARQ worker racing a chat request) previously produced `IntegrityError` 500s. Verified with a two-thread barrier race on each helper: pre-fix 9–20 exceptions per race, post-fix zero, zero duplicate rows.
- **Alternatives rejected**: Postgres `INSERT ... ON CONFLICT` (works, but `catch-IntegrityError → re-SELECT` keeps the code portable and matches existing SQLAlchemy style); adding unique constraints to every table (only `repo_graph` lacked one and had a real duplicate risk).

### D24 — Unique per-run clone directory (multi-user Phase 2)
- **Date**: 2026-08-16
- **Decision**: `GitHubAPIFetcher.fetch_repo` clones into `data/repos/{repo_name}-{12-hex uuid}` — a **unique directory per clone call** — instead of a shared `data/repos/{repo_name}/` dir. `IngestionPipeline.ingest()` now returns `(files, repo_dir)`; the orchestrator, eval harness, and tests consume the returned path and clean it up. The unused `force=True` re-clone path and eval's dead `force_clone` param were removed.
- **Rationale**: Two users ingesting the same repo concurrently shared one clone dir; one orchestrator's `finally: shutil.rmtree()` could delete the other's clone mid-pipeline (corrupt ingest). The per-run dir makes concurrent pipelines safe without serializing them, and partial clones are removed on git-clone failure.
- **Alternatives rejected**: an ingest mutex around the clone (serializes a cheap step and leaves the rmtree hazard to Phase 3's lock anyway); cloning to a stable per-commit dir `data/repos/{hash}` (hash isn't known until after clone).

### D25 — Redis ingest lock with wait-and-reuse (multi-user Phase 3)
- **Date**: 2026-08-16
- **Decision**: New `backend/ingest_lock.py` serializes ingestion per repo **commit**: Redis `SET <ingest_lock:{repo_hash}> <token> NX EX` (owner-token compare-and-del release, heartbeat `renew` so long ingests don't expire it, in-process `threading.Lock` fallback when Redis is down — same degrade-gracefully rule as chat memory). `/api/process` and `/sync` both run `IngestLock.wait_for_index`: the first caller acquires and runs the pipeline in a background thread; a concurrent second caller streams `stage: "waiting"` SSE ticks until the commit is `status='indexed'` (reuse — open a conversation / re-point + tombstone) or **takes over** if the holder released without indexing it. `/api/process`'s skip-to-chat short-circuit now requires `status='indexed'` (`failed`/`indexing`/`deleted` rows are no longer "reused"). Shared SSE queue-drain moved to `backend/sse.py`.
- **Rationale**: Two users ingesting the same repo at the same commit both passed the probe-first pre-check and ran duplicate pipelines (duplicate chunks, double OpenRouter cost, UNIQUE races on `indexed_repo.repo_hash`). The lock keys by commit hash (globally unique), so different commits still ingest in parallel; wait-and-reuse gives the second user the completed result instead of a 409 or wasted work.
- **Alternatives rejected**: in-process-only lock (doesn't help once the app runs multiple uvicorn workers/processes — Redis is already in the stack for the ARQ worker); `409 Already indexing` (worse UX, client must poll); dropping the pipeline's own row-finalize and always "reusing" after a wait (breaks the takeover case where the holder failed and no row exists).

### D26 — Pool sizing + no session across pipeline + thread-safe caches (multi-user Phase 4)
- **Date**: 2026-08-16
- **Decision**: (1) `backend/database.py` pool size is env-tunable (`DB_POOL_SIZE` default 5, `DB_MAX_OVERFLOW` default 10). (2) `_sync_run` no longer holds a `SessionLocal` across the pipeline run (opened only for the pre-check and finalize step, mirroring `_run_pipeline`), and only a `status='indexed'` target row is "reused" — a `failed`/`indexing` row is re-ingested when we hold the lock. (3) `BM25Index` (shared via the `RetrievalPipeline` singleton) is now thread-safe: builds run under a per-commit lock, the cache is a bounded LRU (`BM25_CACHE_SIZE` default 16). (4) The `GET /graph` lazy rebuild is serialized per commit (`_rebuild_lock_for` + double-checked reload), and `graph_builder._PARSERS` is lock-guarded.
- **Rationale**: Background ingests previously pinned a pool connection for their whole (multi-minute) run — with the session now opened only for finalize, steady-state pool usage is short-lived connections, so the default 5+10 pool is comfortable and the ceiling is deploy-tunable. The shared BM25 singleton was mutated without a lock (duplicate builds + dict races on first chat per repo) and cached unboundedly (memory leak as the repo count grows). Concurrent lazy graph rebuilds both built + wrote the same graph.
- **Alternatives rejected**: a single global BM25 build lock (a slow build for one commit would serialize searches on all other commits — per-commit locks keep parallel builds); leaving `repo_graph.repo_hash` uniqueness as the only guard (Phase 1's constraint stops duplicate rows but not duplicate rebuild work); unbounded cache (accepted only as a short-term dev state).

### D27 — Multi-worker uvicorn is the horizontal-scaling lever (multi-user Phase 5)
- **Date**: 2026-08-16
- **Decision**: Production runs `uvicorn --workers ${WEB_CONCURRENCY:-2}` (no `--reload`). The implications are documented in a new root `SCALE.md` + runbook: per-worker in-process caches (BM25 LRU, `lru_cache` singletons, graph rebuild locks, `_PARSERS`) multiply memory ×N; the ingest lock's in-process fallback is **single-process-only** so Redis must be up in multi-worker mode (the Redis primary dedupes across workers); Postgres connections = `N × (DB_POOL_SIZE + DB_MAX_OVERFLOW)`; the ARQ worker scales separately.
- **Rationale**: Infra (Postgres/Qdrant/Redis) is already external and shared; the backend is the only single-process bottleneck. `--workers` is the standard, zero-code way to scale it, and Phases 1–4 removed the cross-process hazards (Redis-backed ingest lock, race-free DB writes, unique clone dirs, per-commit Qdrant scoping) that would have made multi-worker unsafe.
- **Alternatives rejected**: async-everything rewrite (large, risky; sync SQLAlchemy + blocking LLM calls would need async drivers); a single giant process with a bigger thread pool (doesn't use multiple cores, and per-worker memory/cache math still applies).

### D28 — Global ingest concurrency cap (multi-user Phase 6)
- **Date**: 2026-08-16
- **Decision**: `GlobalIngestGate` (in `backend/ingest_lock.py`) caps concurrent pipelines across all users/commits via an atomic Redis counter `ingest_global_active` (Lua incr → ≤ `INGEST_MAX_CONCURRENT` → set TTL, else decr back; Lua floor-0 decr on release; sliding TTL renewed by the pipeline heartbeat so crashed pipelines' slots expire). `INGEST_MAX_CONCURRENT` default 2 (0 disables). `wait_for_index` now returns `owned` only when it holds **both** the per-commit lock and a gate slot — if the cap is full it releases the commit lock and keeps streaming `waiting`; pipeline threads release both in `finally`. Redis down → process-global `BoundedSemaphore` fallback.
- **Rationale**: The per-commit lock dedupes the same commit but distinct commits could still ingest without bound — each pipeline fans out 5 embed + 5 summarize workers against OpenRouter/DeepSeek, so bursts of distinct ingests could trip rate limits / explode cost. A global cap with the same wait-and-reuse UX (`waiting` ticks, not a rejection) protects spend without user-visible failures.
- **Alternatives rejected**: rejecting the request with a 4xx when over cap (worse UX; the user's repo isn't being indexed by anyone and they'd have to retry manually); a per-user cap instead of global (doesn't bound aggregate API spend); a fixed-size worker pool for pipelines (a Redis counter keeps it cross-worker and crash-safe without a queue).

### D29 — `/api/reset` requires auth (multi-user hardening)
- **Date**: 2026-08-16
- **Decision**: `POST /api/reset` (wipes both Qdrant collections + index tables) now requires a Clerk JWT via `Depends(get_current_user)`; unauthenticated callers get 401.
- **Rationale**: The endpoint was unauthenticated — any caller (even outside the app) could wipe all index data. In a multi-user deployment that's an obvious denial-of-service/corruption vector; the frontend never calls it (`resetAll` is an unused helper), so gating it costs nothing.
- **Alternatives rejected**: an admin/role check (no role model exists yet — auth is the minimal correct gate); removing the endpoint entirely (it's a useful dev/admin tool).

### D30 — Production infra: `compose.prod.yml` + managed-service doc (multi-user Phase 8)
- **Date**: 2026-08-16
- **Decision**: Added `compose.prod.yml` (self-hosted prod infra: the same Qdrant/Postgres/Redis with healthchecks, restart policies, resource hints, and Redis AOF persistence) and `PRODUCTION.md` (managed-service alternatives — RDS/Cloud SQL, Qdrant Cloud, ElastiCache/Upstash — plus HA/backup guidance and `max_connections` planning). The Qdrant healthcheck uses bash `/dev/tcp` HTTP GET against `/healthz` because the `qdrant/qdrant:v1.17.0` Debian image ships no curl/wget; verified all three services reach `healthy`.
- **Rationale**: The app's state lives entirely in Postgres/Qdrant/Redis, so the backend + ARQ worker are stateless and can run anywhere — a small self-hosted compose file plus a managed-service reference covers both deployment shapes without containerizing the app itself.
- **Alternatives rejected**: adding the backend/ARQ worker to the compose file (would require Dockerfiles — out of scope; they run as ordinary services); skipping a prod compose file (healthchecks/restart policies are the minimum an orchestrator needs).

### D31 — Deployment hardening: CORS env, `/api/ready`, threadpool size (multi-user Phase 9)
- **Date**: 2026-08-16
- **Decision**: (1) CORS origins are env-configurable via `CORS_ORIGINS` (comma-separated; default = the Vite dev origins). (2) New `GET /api/ready` readiness probe — 200 only when Postgres (`SELECT 1`), Qdrant (collections), and Redis (ping) are all reachable, else 503 with a per-dep `checks` map; `/api/health` stays the no-dependency liveness probe. (3) `THREADPOOL_SIZE` (default 40) sizes FastAPI's sync-endpoint thread pool per worker, applied in the lifespan via `anyio.to_thread.current_default_thread_limiter()`. Verified live: `/api/ready` 200 all-up → 503 with `redis:false` when Redis is stopped → 200 after restore; CORS echoes an allowed origin and omits the header for a disallowed one; threadpool 40 by default, 64 under `THREADPOOL_SIZE=64`.
- **Rationale**: Hardcoded localhost CORS would reject a production frontend (or worse, silently misbehave); a readiness probe is what orchestrators/load balancers gate on; and the chat concurrency ceiling is otherwise fixed at FastAPI's hidden 40-thread default.
- **Alternatives rejected**: a single `/api/health` that also pings deps (breaks liveness semantics — a dep blip would evict a healthy worker); async chat rewrite for concurrency (sync SQLAlchemy + blocking LLM calls; threadpool + `--workers` are the pragmatic levers, per D27).

### D33 — MRR added; Context Precision kept with its 1/K ceiling documented
- **Date**: 2026-08-16
- **Decision**: Added **MRR** (mean reciprocal rank of the first relevant chunk) as a fourth retrieval metric — `reciprocal_rank` in `evaluation/metrics.py`, reported in every retrieval table, the component-delta tables, the per-query breakdown (`R/P/MRR`), and the aggregate report. Context Precision is **kept**, and the report now states its structural ceiling explicitly: with one target entity per question and K chunks returned, the max is `1/K` (computed from `meta.k`, e.g. 0.125 at K=8), framed as "measures noise, not rank quality". The retrieval trio is now Recall (found) / MRR (rank quality) / Recall@K (hit).
- **Rationale**: Context Precision was structurally capped at ~1/K because each golden question targets a single entity and the pipeline always returns K chunks — so it hovered around 0.125 and could never reach 1.0, making it a confusing headline that looked like bad retrieval. MRR fixes the scale (top hit = 1.0, rank 2 = 0.5, absent = 0) and measures the rank-quality question users actually care about. Precision was not dropped outright because it still conveys the noise/over-breadth signal and the user preferred continuity.
- **Alternatives rejected**: replacing Context Precision with MRR (user preferred keeping both); replacing it with Precision@1 (coarser — no partial credit, ranks 2–8 all score 0); dropping precision with no replacement (loses the noise signal).

### D34 — App verified working as intended (eval closeout)
- **Date**: 2026-08-16
- **Decision/record**: The lynko re-run on the corrected harness (`data/eval_reports/lynko_20260816_133243/`, N=20, K=8) confirms the pipeline works as intended. Production setup S4: Recall@K **1.000**, MRR **0.975**, Context Recall **1.000**, Target-in-context **0.95**, Answer Relevance **1.000**, Faithfulness **0.821**. S2 > S1 (MRR 0.713 vs 0.427) and S4 > S3 (0.975 vs 0.459) confirm semantic chunking and reranking each earn their place; S3 < S2 (hybrid fusion hurting on keyword-light repos) remains an open item (TODO). The previous lynko report (`lynko_20260815_112355/`) was deleted — it predated the strict-overlap/judge fixes (D15–D18) and MRR (D33).
- **Rationale**: Faithfulness 0.948→0.821 vs the pre-fix run reflects the **stricter D16 judge**, not lost retrieval — target-in-context held at 0.95, so ground truth reached the LLM almost always. This closes out the evaluation work: the harness (strict overlap, MRR, judge sanity gate) now produces trustworthy numbers and the app is confirmed working as intended.
- **Alternatives rejected**: re-running the other three repos (express/requests/ripgrep) now for a full MRR aggregate (deferred to TODO — not needed to confirm the app works; their reports predate MRR and would need re-embed-free re-runs).

### D35 — PDF export via WeasyPrint (optional, graceful skip)
- **Date**: 2026-08-16
- **Decision**: `write_report` and `write_aggregate` now also emit `report.pdf` / `aggregate.pdf` by rendering the existing self-contained HTML through **WeasyPrint** (new `requirements.txt` dep; `_render_pdf` helper in `evaluation/report.py`). WeasyPrint applies the report's `@media print` CSS (table overflow made visible, `break-inside: avoid` on figures/rows). PDF is **optional**: if WeasyPrint or a system library it needs is unavailable, the renderer logs a warning and skips the PDF — the JSON/MD/HTML outputs and the run still succeed.
- **Rationale**: Resolves the "PDF deferred" note in D8. The report HTML is already self-contained (inline CSS + base64 figures), so WeasyPrint renders it directly with no template duplication and no browser subprocess; the graceful skip keeps the harness's "never fails a run" contract intact on machines without the system libs.
- **Alternatives rejected**: Chromium headless `--print-to-pdf` (zero Python dep and pixel-perfect, but a brittle system-binary dependency + subprocess shelling); making PDF opt-in via a `--pdf` flag (unnecessary — the graceful skip already makes always-on safe); reportlab (would duplicate the HTML/CSS as a second render path).


### D32 — All prompt templates consolidated into a single root module
- **Date**: 2026-08-16
- **Decision**: New root `prompts.py` is the single source of truth for every LLM prompt template in the project. All system prompts (RAG answer generation, file summarization, chat-memory rolling summaries, node explanation, the eval judges, golden-set paraphrase) and all user-prompt templates were moved there as named constants + small pure template functions; the six consumers (`rag/prompt_builder.py`, `summarization/file_summarizer.py`, `memory/worker.py`, `backend/routers/repositories.py`, `evaluation/llm_judge.py`, `evaluation/golden_set.py`) now import from it and keep only their assembly logic (message-list construction, retry loops, context grouping). Prompt output is byte-identical to the pre-move text (verified with an equivalence script).
- **Rationale**: Prompt text was scattered across 6 files in 5 packages; every significant prompt tweak (e.g. D14, D16, D19) previously required editing whichever file owned the string, making prompt changes hard to audit, version, and tune in one place. A root module is importable by every consumer (all invocations already run from the repo root) and keeps prompt work discoverable.
- **Alternatives rejected**: a `prompts/` package with per-domain modules (more files than the problem warrants); `rag/prompts.py` (natural for RAG but makes eval/summarization/memory depend on `rag` for unrelated text); leaving prompts inline (the problem being fixed).

### D36 — Evaluation work concluded
- **Date**: 2026-08-16
- **Decision/record**: The evaluation harness work is concluded. Complete state: four pipeline setups (S1–S4), six metrics (Context Recall/Precision, MRR D33, Recall@K, Faithfulness, Answer Relevance), span-based strict-overlap relevance (D15), judge protocol + sanity gate (D16), symbol-leakage filter (D17), variance + target-in-context reporting (D18), PDF export via WeasyPrint (D35), CLI progress bars, and a no-API smoke test (`tests/test_11_evaluation.py`, 13 checks green). The pipeline is confirmed working as intended by the live lynko run (D34). Remaining ideas (re-run the other repos for an MRR aggregate, ripgrep S2<S1 investigation, golden-set curation, judge discrimination test, RRF tuning, config schema validation, graded recall curve) are explicitly **deferred to `TODO.md`**, not part of this conclusion.
- **Rationale**: The harness now produces trustworthy, reproducible numbers and the app is verified working as intended; continuing to add optional experiments would be scope creep beyond the evaluation deliverable. Deferred items are tracked so nothing is lost.
- **Alternatives rejected**: continuing the deferred experiments before concluding (each is optional polish, not required for the eval's purpose); removing the harness (it is the project's regression tool for retrieval/generation quality).

### D37 — Per-user 24h usage caps + repo-size gates (Phase 1: ledger & core)
- **Date**: 2026-08-21
- **Decision**: Cost-bearing actions are capped per user in a **rolling 24h window** via a new `usage_events` ledger (`backend/usage.py`): actions are grouped so one limit covers several recorded actions — `ingest` (`USAGE_INGEST_MAX`=2: `repo_ingest` pipeline runs + `repo_sync` re-ingests) and `message` (`USAGE_MESSAGE_MAX`=20: both chat endpoints + `explain`). Zero-spend reuse paths (skip-to-chat reuse of an already-indexed commit, up-to-date sync no-op) never count. A repo-size gate bounds a single ingest at `USAGE_MAX_REPO_FILES`=300 files / `USAGE_MAX_REPO_CHUNKS`=6000 chunks. Counts are Postgres `COUNT`s (correct across workers, no Redis), `check_usage` is the pre-spend 429 gate, `record_usage` appends after budget is spent (never raises).
- **Rationale**: The user pays all API spend (OpenRouter embeds/summaries + DeepSeek generation), so the cap protects cost while keeping the app usable. Per-action counts in a durable Postgres ledger (rather than Redis counters) survive restarts, scale across workers without the ingest lock's single-process caveat, and need no new infra. The size gates are placed **before any LLM/embed spend** (files after scan, chunks after local chunking) so a rejected repo costs nothing. Limits were chosen to be generous-but-bounded: they cover every repo tested so far (Gungale 24f/259c, Aircraft-instructor 40f/839c, ripgrep ≈180f/3556c) while blocking frameworks/monorepos (Django/NumPy/CPython are 1000–2000+ files).
- **Alternatives rejected**: Redis counters (volatile, and a Redis-down degrade path would make caps unreliable); calendar-day window (midnight cliff); cost-estimate/token-based caps (significantly more complex; counts bound spend well enough at these low limits); capping free read endpoints (no spend — noise); recording only successful pipelines (a size-rejected clone is cheap to re-attempt and burning a slot is mildly anti-abuse); capping the eval harness (dev CLI, not user-facing API).
- **Note**: The boundary is intentionally soft under a race — two requests that both pass `check_usage` at exactly the limit can both proceed (overshoot bounded by concurrency, negligible at these limits). Enforcement is wired in the endpoints (`check_usage` pre-spend; `record_usage` at the spend point — owned pipeline start for ingest/sync, completed streams for chat/explain) and the size gates in the orchestrator (Phase 2–3).

### D38 — Embed-API outage degrades to BM25-only retrieval (never breaks chat)
- **Date**: 2026-08-21
- **Decision**: `RetrievalPipeline.retrieve` wraps query embedding + hybrid retrieval in `try/except`. When the embed API (OpenRouter) is unreachable — e.g. the transient DNS failure that surfaced as a 500 on `/api/chat/stream` — it falls back to **BM25-only keyword retrieval** (`bm25_index.search`, local + Qdrant-backed, no external call), logs `stage=query_embed_failed falling_back_to_bm25_only`, and tags every result `degraded: "bm25_only"`. The existing rerank fallback (D13) then also fires during the same outage (`reranked: False`). Covers both `/api/chat` and `/api/chat/stream` via the shared `retrieve()`. The eval harness's S4 mirror was intentionally **not** updated (dev tool; a failing eval run during an outage is acceptable and self-explanatory).
- **Rationale**: Chat already degrades gracefully everywhere else — rerank → hybrid (D13), long-term memory → no memory. Query embedding was the one unguarded external call in the chat path, so an embed outage 500'd the whole endpoint. BM25 is entirely local, so it's a reliable degraded mode whenever Qdrant is up; keyword-only quality is the accepted trade for availability.
- **Alternatives rejected**: letting chat 500 on embed outage (the bug); degrading to empty results (worse than BM25, and chat would still work but with no grounding); adding a retry layer (a `ConnectionError` has no HTTP status to retry on, and the outage is environmental); mirroring the degrade into eval S4 (scope creep for a dev tool — deferred).



