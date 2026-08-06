# frontend/src/api/

## Purpose
Axios-based API client layer for all backend communication. Handles auth token injection, error normalization, and endpoint helpers.

## Ownership
- `client.js` — Axios instance, request interceptor (Clerk Bearer token), response interceptor (error normalization), typed endpoint functions

## Local Contracts
- Base URL is `/api` (proxied by Vite dev server to `localhost:8000`)
- Token provider set via `setTokenProvider(getToken)` from `App.jsx`
- All endpoint functions return parsed data (not Axios response wrapper)
- Errors normalized to `Error(message)` from `response.data.detail` or `response.data.message`
- No endpoint functions for unimplemented backend routes yet (will error gracefully)
- Repo-scoped helpers: `getRepoGraph(repoName)` and `getFileSummary(repoName, filePath)` hit `/repositories/{repo}/graph` and `/repositories/{repo}/summary`

## Work Guidance
- Add new endpoint functions following existing pattern: `export async function getFoo() { const { data } = await client.get("/foo"); return data; }`
- Do not import `client` directly outside this file — use the exported functions

## Verification
- Imported and used by `src/pages/AppPage.jsx` and `src/pages/SettingsPage.jsx`
- Build checked via `npm run build`
