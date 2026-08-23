# TODO — Task Tracker

Working task list for the project, **ranked by importance (most → least)**. Completed work is recorded in git history and `DECISIONS.md` (D1–D38) — it is not tracked here. Symbol-graph plan lives in `PLAN.md`; schema/identity reference lives in `DB_SCHEMA.md`.

---

## High

1. **Security: purge `.env.local` from git history** — `.env.local` (with a real `CLERK_SECRET_KEY`) was tracked in git history before deletion. It's gone from the working tree but still in history — `git rm --cached .env.local` + history purge/rotation if this repo ever goes public.

2. **Smoke tests review** — run/update `tests/test_0*.py` against the current model. `test_05_retrieval` was updated for `repo_url`; the rest haven't been run end-to-end (full-pipeline tests that cost API calls).

3. **Full live verification** — infra up, then run `tests/test_01`…`test_09` + `test_10`; `./dev.sh` smoke; Graph view render + chat RAG on an existing repo.

4. **Tombstone purge** — `status='deleted'` rows + their retained chunks only get cleaned up when a conversation is deleted (citations cascade). Purge tombstones + retained chunks when the citations' messages are deleted — otherwise old-commit storage grows unboundedly.

## Medium

5. **Repos list UI** — `GET /api/repositories` already returns one `RepoOut` per repo (latest commit, `repo_hash`, `status`, counts) but the frontend never renders it; repos surface only via conversations + the header Sync button. Add a small repos panel (per-repo `updates_available` + Sync + status). Optionally fold the `updates` probe into the list response instead of the separate endpoint.

6. **Usage-cap quota display** — expose `GET /api/usage` (already backed by `usage_status` in `core/usage.py`) and show remaining quota in the UI (settings/header). Optional `USAGE_MAX_REPO_BYTES` knob if a byte cap is wanted.

7. **Real-repo spot checks** — ingest one repo per major language (Python, JS/TS, C/C++, Rust, Go, C#, Ruby, Java, Kotlin) and eyeball the graph: entity coverage, containment, imports, scoped refs.

8. **`GET /graph` stale-rebuild e2e** — confirm a pre-existing persisted graph rebuilds when its `version` is below `GRAPH_VERSION`.

9. **Re-run eval on the current harness** — express / requests / ripgrep for a clean 4-repo aggregate with MRR (cached golden sets + embedded data, no re-embed cost); also live runs for requests/fastapi if more data is wanted.

10. **Judge discrimination test** — inject a known-bad answer to verify the judge actually penalizes it (Answer Relevance is currently 1.000 on all items).

## Low / research / polish

11. **Jump-to-current-version for citations** — after sync, old cited chunks open fine (retained), but "jump to the current version" of a changed file isn't implemented. Best-effort lookup by `(repo_hash, file_path)` + `symbol`, line-overlap fallback since lines shift on sync.

12. **Investigate ripgrep S2 < S1** — on ripgrep, AST vector (0.545 R@K, R@1 = 0.000) trails naive (0.818); hypothesis: large Rust functions/impls produce big diluted AST chunks. Check chunk-size distribution vs requests/express and whether the token-aware AST splitter needs tuning for Rust.

13. **Golden-set curation pass** — review LLM-paraphrased queries in `evaluation/datasets/*.json`; drop/rewrite queries that leak the symbol name or are unanswerable.

14. **RRF/hybrid tuning experiment** — S3 < S2 on lynko: test RRF `k`/candidate-pool sizes or drop lexical fusion on keyword-light repos.

15. **Generation metrics on S3** — compare S3 vs S4 answer quality (currently S4 only, per D3).

16. **Context token-saving preset** — if token cost matters, enable `RAG_CONTEXT_MIN_SCORE_RATIO=0.4` + `RAG_CONTEXT_MAX_PER_FILE=2` as an opt-in preset (D14).

17. **Recall curve definition** — graded recall variant (relevant-in-top-K / total-relevant) as an optional figure alongside the binary hit-rate curve (D12).

18. **Config schema validation** — type-check `--config` JSON keys instead of trusting them.

19. **Legacy message backfill (optional)** — pre-feature `messages` rows have `repo_hash = NULL`. Backfill from the `citation` table (assistant messages: own citation rows; user messages: inherit the next assistant message's hash). Data-cleanup nicety only — no effect on the divider or behavior.
