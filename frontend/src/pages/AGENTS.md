# frontend/src/pages/

## Purpose
Page-level components mapped to routes. Each page composes components from `src/components/` and manages its own state and data fetching.

## Ownership
- `LandingPage.jsx` — Route `/` (public). Full marketing page: hero, features, how-it-works, footer. Self-contained GSAP scroll animations.
- `AppPage.jsx` — Route `/app` (protected). Main app: sidebar + repo input / progress / chat UI. Manages pipeline state, conversation CRUD, SSE streaming chat, polling.
- `SettingsPage.jsx` — Route `/settings` (protected). User profile display and name editing via Clerk + backend API.

## Local Contracts
- Pages are the only components that manage state and side effects (API calls, timers, SSE)
- Pages compose children from `src/components/` and pass props downward
- Protected routes are enforced by `ProtectedRoute` wrapper in `src/App.jsx` — not by the pages themselves
- `AppPage` handles the full app state machine: idle → processing → ready (chat)
- `AppPage` owns SSE streaming, status polling, conversation CRUD, message state
- Settings page reads user profile from `GET /api/users/me` and writes via `PATCH /api/users/me`

## Work Guidance
- New routes: create page in this directory, add `<Route>` entry in `src/App.jsx`
- Keep page-fetch logic in the page, not in components
- Use `src/api/client.js` functions for API calls; fall back to raw `fetch` only for SSE streaming (needs `ReadableStream` reader)
- Pages should handle their own loading/empty/error states

## Verification
- Routes tested manually via Vite dev server
- Build verified with `npm run build`
