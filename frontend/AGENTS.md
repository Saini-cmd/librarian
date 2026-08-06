# frontend/

## Purpose
React 18 SPA for repo ingestion and chat with the RAG system. Features a brutalist industrial design with daisyUI 5 + Tailwind CSS 4.

## Ownership
- `src/main.jsx` — React entry point, ClerkProvider + BrowserRouter
- `src/App.jsx` — Router (/, /app, /settings), protected routes, token provider
- `src/styles.css` — Tailwind + daisyUI + typography plugin imports, brutalist-dark theme, scanline/noise effects
- `src/pages/` — Page-level components (LandingPage, AppPage, SettingsPage)
- `src/components/` — Reusable UI components (Sidebar, Layout, ChatMessages, etc.)
- `src/api/client.js` — Axios instance with auth interceptor + endpoint helpers
- `src/hooks/` — Custom React hooks (useMarkdown, useApi)
- GSAP scroll animations on LandingPage sections via `useGSAP` / `useLayoutEffect` + `ScrollTrigger.batch()`
- `vite.config.js` — Dev server config with Tailwind CSS v4 plugin and API proxy

## Routes
| Path | Page | Auth |
|---|---|---|
| `/` | LandingPage | Public |
| `/app` | AppPage | Protected (Clerk) |
| `/settings` | SettingsPage | Protected (Clerk) |

## Local Contracts
- Dev server on port 5173, proxies `/api` to `http://127.0.0.1:8000`
- Chat responses streamed via Server-Sent Events
- Uses `marked` for markdown rendering and `dompurify` for sanitization; assistant messages are styled with `@tailwindcss/typography` (`prose prose-invert prose-sm`) for well-spaced paragraphs/headings/lists/code/tables
- daisyUI 5 with custom `brutalist-dark` theme — all radius 0, thick borders
- Brutalist design system: Tactical Telemetry Dark mode, neon green accent, monospace data typography
- API calls go through Axios instance in `src/api/client.js` with automatic Clerk Bearer token injection
- Auth token provider set via `setTokenProvider()` in App.jsx

## Design System
- **Theme:** `brutalist-dark` (custom daisyUI theme, Tactical Telemetry Dark)
- **Colors:** Dark substrate (oklch 13% 0 0), white phosphor text, neon green primary/accent (oklch 68% 0.33 145)
- **Typography:** Inter (headers, black weight 900, uppercase), JetBrains Mono (data, UI, monospace)
- **Corners:** 0px border-radius everywhere (brutalist 90° only)
- **Borders:** 2px solid borders for compartmentalization
- **Effects:** Green CRT phosphor scanline overlay (rgba 0,255,65,0.07) + SVG mechanical noise grain (3% opacity)
- **Layout:** CSS Grid with visible compartmentalized sections
- **Animation:** GSAP with ScrollTrigger — hero timeline on mount, scroll-reveal for section content (badge → heading → cards)

## Work Guidance
- Keep API interaction through the proxy path (`/api/...`) via Axios client in `src/api/client.js`
- New pages go in `src/pages/`, new shared components in `src/components/`, new hooks in `src/hooks/`
- Use `useGSAP` from `@gsap/react` for scroll animations; register `ScrollTrigger` once in `App.jsx`
- All daisyUI component classes must come from daisyUI 5 docs — Tailwind utility overrides for anything custom
- Brutalist rules: no border-radius anywhere, 2px borders for compartmentalization, uppercase headers, monospace data

## Verification
- `npm run dev` starts Vite dev server
- `npm run build` for production build

## Child DOX Index

| Path | Purpose |
|---|---|
| `src/api/` | Axios instance, auth interceptor, endpoint helpers |
| `src/components/` | Reusable daisyUI + GSAP components (Layout, Sidebar, ChatMessages, Landing sections) |
| `src/hooks/` | Custom React hooks (useMarkdown, useApi) |
| `src/pages/` | Route-level pages (Landing, App, Settings) |
