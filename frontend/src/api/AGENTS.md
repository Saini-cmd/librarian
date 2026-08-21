# frontend/src/api/

## Purpose
Axios-based API client layer for all backend communication. Handles auth token injection, error normalization, and endpoint helpers.

## Ownership
- `client.js` — Axios instance, request interceptor (Clerk Bearer token), response interceptor (error normalization), typed endpoint functions
- `sse.js` — `consumeSSE(response, onEvent)` — minimal SSE reader (splits on `\n\n`, parses `data:` JSON lines, calls `onEvent`; non-JSON payloads skipped, handler errors propagate). Used for `/api/process` and `/sync` progress streaming. `readError(response)` — parses a non-SSE error body into `{message, quota}`; `quota` is `{group, used, limit, resets_at}` for a usage-cap 429 (the ledger gate in `backend/usage.py`) else null. Handles FastAPI `{detail: str}` and the 429 `{detail: {detail, group, used, limit, resets_at}}` (message appends `(used/limit used)` when quota). Used by the fetch-based SSE consumers when `!res.ok` to route quota 429s to the `QuotaNotice` UI

## Local Contracts
- Base URL is `/api` (proxied by Vite dev server to `localhost:8000`)
- Token provider set via `setTokenProvider(getToken)` from `App.jsx`
- All endpoint functions return parsed data (not Axios response wrapper)
- Errors normalized to `Error(message)` from `response.data.detail` or `response.data.message`
- No endpoint functions for unimplemented backend routes yet (will error gracefully)
- **Long-running actions stream**: `/api/process` and `/api/repositories/{repo_hash}/sync` are SSE streams (NOT axios helpers) — consumed via raw `fetch` + `consumeSSE`. Axios has no streaming support, so there is no `processRepo`/`syncRepo` helper
- **Repo identity = `repo_hash`**: repo-scoped helpers take the commit hash — `getRepoGraph(repoHash)`, `getFileSummary(repoHash, filePath)` hit `/repositories/{repo_hash}/graph` and `/summary`; `getChunk(repoHash, chunkId)` hits `/repositories/{repo_hash}/chunks/{chunkId}` (full chunk incl. `content`) for clickable chat citations; `getFileChunks(repoHash, filePath)` hits `/repositories/{repo_hash}/chunks?file_path=` (all chunks for a file, line-sorted) for the graph panel's complete-code view
- `getRepoUpdates(repoHash)` → `GET /repositories/{repo_hash}/updates` (returns `{updates_available, remote_hash}`)

## Work Guidance
- Add new endpoint functions following existing pattern: `export async function getFoo() { const { data } = await client.get("/foo"); return data; }`
- Do not import `client` directly outside this file — use the exported functions

## Verification
- Imported and used by `src/pages/AppPage.jsx` and `src/pages/SettingsPage.jsx`
- Build checked via `npm run build`
