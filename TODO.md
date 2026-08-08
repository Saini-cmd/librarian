# TODO — Task Tracker

Working task list for the project. Check items off as they land; add side tasks as they come up. Replacements for the old `PLAN.md` — schema/identity reference lives in `DB_SCHEMA.md`.

---

## Remaining sync-feature work

- [ ] **Repos list UI** — `GET /api/repositories` already returns one `RepoOut` per repo (latest commit, `repo_hash`, `status`, counts) but the frontend never renders it; repos surface only via conversations + the header Sync button. Add a small repos panel (per-repo `updates_available` + Sync + status). Optionally fold the `updates` probe into the list response instead of the separate endpoint.
- [ ] **Jump-to-current-version for citations** — after sync, old cited chunks still open fine (retained), but a "jump to the current version" of a changed file isn't implemented. Best-effort lookup by `(repo_hash, file_path)` + `symbol`, line-overlap fallback since lines shift on sync. No snippet stored (a full `/api/reset` wipes cited chunk content too).
- [ ] **Tombstone purge** — `status='deleted'` rows + their retained chunks only get cleaned up when a conversation is deleted (citations cascade). Purge tombstones + retained chunks when the citations' messages are deleted.
- [ ] **Smoke tests review** — run/update `tests/test_0*.py` against the new model. `test_05_retrieval` was updated for `repo_url`; the rest haven't been run end-to-end (full-pipeline tests that cost API calls).
- [ ] **Legacy message backfill (optional)** — the pre-feature `messages` rows have `repo_hash = NULL`. Backfill from the `citation` table (assistant messages: own citation rows; user messages: inherit the next assistant message's hash). Data-cleanup nicety only — no effect on the divider or behavior.

---

## Side tasks / housekeeping

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
