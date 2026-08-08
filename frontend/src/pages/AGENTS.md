# frontend/src/pages/

## Purpose
Page-level components mapped to routes. Each page composes components from `src/components/` and manages its own state and data fetching.

## Ownership
- `LandingPage.jsx` — Route `/` (public). Full marketing page: hero (with animated clay shapes), features (bento grid), how-it-works, footer. Self-contained GSAP scroll animations.
- `AppPage.jsx` — Route `/app` (protected). Main app: sidebar + repo input / progress / chat UI. Manages pipeline state, conversation CRUD, SSE streaming (chat + process/sync progress), and the open citation popover state (`openCitation` = citation + anchor rect, passed to `CitationCard`)
- `SettingsPage.jsx` — Route `/settings` (protected). User profile display and name editing via Clerk + backend API.

## Local Contracts
- Pages are the only components that manage state and side effects (API calls, timers, SSE)
- Pages compose children from `src/components/` and pass props downward
- Protected routes are enforced by `ProtectedRoute` wrapper in `src/App.jsx` — not by the pages themselves
- `AppPage` handles the full app state machine: idle → processing → ready (chat)
- On ingest completion, `AppPage` does NOT inject an assistant "ready" bubble — it just flips to `ready` and lets `ChatMessages` show its centered empty-state "Ready to chat" label, which disappears on the first user message
- `AppPage` owns SSE streaming (chat, **and ingestion/sync progress via `consumeSSE`**), conversation CRUD, message state. No `/api/status` polling — `/api/process` and `/api/repositories/{repo_hash}/sync` stream `progress` events until a final `result`/`error` event
- Conversation selection: on ingest, `AppPage` sets `activeConvId` from `/api/process`'s `conversation_id`; opening an already-indexed repo creates a fresh conversation via `createConversation` (new entry each open); clicking a sidebar entry opens its history (messages + citations) via `GET /api/conversations/{id}`
- Chat streaming: the SSE reader captures the final `citations` event and attaches it to the assistant message; historical messages load their `citations` from `GET /api/conversations/{id}`. Citation clicks open a `CitationCard` popover (state in `AppPage`, cleared on new chat / new message / conversation switch / view switch)
- Chat layout is a fixed-height viewport shell (`h-dvh overflow-hidden` on the app root): the header and the message input/send form are pinned (input never moves off-screen during streaming), and only the `ChatMessages` list scrolls internally as answers grow upward
- Client-side message ids for newly sent messages use a monotonic ref counter (`local-{n}`) — never `Date.now()` — so streamed token updates (which match the placeholder by id) can never collide with or leak into the user's message bubble under rapid/double sends; a single `setMessages` appends both the user message and the assistant placeholder
- Chat is repo-aware: `AppPage` loads `GET /api/repositories` and sends `repo_hash` with each message; the chat header shows the active repo name as static text (no in-chat repo switching)
- Header: left side shows the **active repo name as the heading** (truncates); right side holds a **Sync button + "Update available" badge** (driven by `getRepoUpdates`) and a **segmented control** (Chat ⇄ Graph pills, iOS style). Graph view fetches `getRepoGraph(selectedRepoHash)` lazily (cached per hash in state) and renders `SymbolGraphView`; chat messages are preserved when switching views
- **Sync**: clicking Sync calls `POST /api/repositories/{repo_hash}/sync` via `consumeSSE`; a **full-screen overlay** (`fixed inset-0 z-50`, `bg-base-100/90`) shows a `ProgressBar` driven by `syncProgress`/`statusText` while `syncing` is true (separate from the inline ingestion `ProgressBar`). `up_to_date` toasts a message, `synced` refreshes repos + conversations and reloads the active conversation (its `repo_hash` moved to the new commit)
- Chat composer is a **floating glass pill** (`.glass-composer`, rounded-full) with a circular send button, pinned below the message list; message list scrolls internally (`min-h-0`) in the fixed `h-dvh` shell
- The landing view for all users is the repo-input (start) page; the side pane lists the user's past conversations for navigation, and the single `+ Ingest New Repo` button returns to the start page
- No re-ingest: pasting a repo URL already in `repositories` opens a fresh chat on it directly; the backend independently short-circuits via a **global commit-hash probe** (`git ls-remote` HEAD vs `indexed_repo.repo_hash`) — commits indexed by any user are reused, and an unchanged repo never re-runs the pipeline (clone + chunk + summarize + embed is cost-heavy). A changed repo gets a new commit; the header Sync button pulls it in and tombstones old commits
- Settings page reads user profile from `GET /api/users/me` and writes via `PATCH /api/users/me`

## Work Guidance
- New routes: create page in this directory, add `<Route>` entry in `src/App.jsx`
- Keep page-fetch logic in the page, not in components
- Use `src/api/client.js` functions for API calls; fall back to raw `fetch` only for SSE streaming (needs `ReadableStream` reader)
- Pages should handle their own loading/empty/error states

## Verification
- Routes tested manually via Vite dev server
- Build verified with `npm run build`
