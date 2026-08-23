# frontend/

## Purpose
React 18 SPA for repo ingestion and chat with the RAG system. Themeable design-system frontend — default `clay` (claymorphism: soft, puffy 3D surfaces), with `apple-glass` (iOS glass), `brutalist-dark`, and `glass` presets. Built on daisyUI 5 + Tailwind CSS 4; guided by installed skills (`claymorphism`, `ios-glass-ui-designer`).

## Ownership
- `src/main.jsx` — React entry point, ClerkProvider + BrowserRouter
- `src/App.jsx` — Router (/, /app, /settings), protected routes, token provider
- `src/styles.css` — CSS entry: imports Tailwind, daisyUI, typography plugin + the design system
- `src/styles/design-system.css` — **the single design-system template**: all daisyUI theme palettes (`clay` default, `apple-glass`, `brutalist-dark`, `glass`), `--ds-*` design tokens (fonts, **`--ds-root-font-size` = global text-scale knob** — flip one value to resize the whole app, glow, scanlines, glass surface, clay surface, symbol-graph colors), effect/glass utilities (`.glass-panel`, `.glass-surface`, `.glass-nav`, `.glass-composer`, `.glass-card`, `.glow`, `.graph-surface`, `.scanlines`, `.noise`), **clay utilities** (`.clay`, `.clay-press`, `.clay-ring` — puffy 3D shadows derived from `--ds-clay-*` tokens), base layer (headings use `--ds-font-display`; `html` reads `--ds-root-font-size`), and `@theme` mapping so `font-sans`/`font-mono`/`border-2`/`rounded-none` follow the active theme — breakpoints are **locked to fixed px** in `@theme` so they don't drift when `--ds-root-font-size` changes
- `src/theme/` — theme switching (`DEFAULT_THEME`, `applyTheme`) + `useGraphTheme` (reads graph colors + React Flow color-mode from CSS tokens)
- `src/pages/` — Page-level components (LandingPage, AppPage, SettingsPage)
- `src/components/` — Reusable UI components (Sidebar, Layout, ChatMessages, etc.)
- `src/icons/` — Curated SVG icon set as React components (`Icon.jsx` registry + named exports, all `fill="currentColor"` for theme-driven color)
- `src/api/client.js` — Axios instance with auth interceptor + endpoint helpers
- `src/api/sse.js` — `consumeSSE` reader for `/api/process` + `/sync` progress streaming
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
- daisyUI 5 with `clay` theme (default, light claymorphism) + `apple-glass`, `brutalist-dark`, `glass` presets — all palette, radius, border and font decisions live in `src/styles/design-system.css`
- **Theme switching**: active theme = `data-theme` on `<html>`; set `DEFAULT_THEME` in `src/theme/index.js` to switch, and add a `@plugin "daisyui/theme"` block + `[data-theme="name"]` token override in `design-system.css` for a new theme. `applyTheme()` is called once in `main.jsx`
- **Fonts**: Montserrat (sans body) + Poppins (display/headings) + JetBrains Mono (mono) loaded in `index.html` and wired via `@theme { --font-sans/--font-mono: var(--ds-*) }` + `--default-font-family`; headings inherit `--ds-font-display` (base layer rule)
- **No hardcoded colors/chrome in components**: components use daisyUI semantic classes or `--ds-*` tokens only. `border-2` and `rounded-none` are remapped in `@theme` to `var(--border)`/`var(--radius-box)` so chrome is theme-driven. Clay surfaces use `.clay`/`.clay-press` (shadows only — background/radius come from utilities); glass surfaces use `.glass-*`
- **Design intent**: claymorphism (default) — playful, puffy 3D surfaces, soft colors, rounded, no harsh borders; `apple-glass` — restrained functional glass, neutral palette, one accent
- API calls go through Axios instance in `src/api/client.js` with automatic Clerk Bearer token injection
- Auth token provider set via `setTokenProvider()` in App.jsx

## Design System
- **Theme (default):** `clay` — light claymorphism, soft lavender base, white puffy surfaces, system-blue primary, large radii (1.5rem boxes), 1px hairline, soft depth; puffy 3D depth via `.clay`/`.clay-press` dual inset-highlight + drop shadows
- **Alternate themes:** `apple-glass` (light iOS glass), `brutalist-dark` (dark terminal, 2px square, neon green), `glass` (dark violet glassmorphism) — switch via `DEFAULT_THEME`
- **Fonts:** Montserrat (body), Poppins (display/headings), JetBrains Mono (mono, data)
- **Global text scale:** `--ds-root-font-size` in `design-system.css` (default 18px) — flip this single value to resize the whole app; Tailwind breakpoints are px-locked so `lg`/`md` stay at 1024/768px
- **Corners:** rounded — selectors 1rem, fields 1rem, boxes 1.5rem (`--radius-*` tokens)
- **Borders:** 1px hairline (`--border`) with low-contrast edges; clay relies on shadows, not borders
- **Clay surfaces:** `.clay` (cards/blobs) and `.clay-press` (buttons, with press-down active state) — shadows only, compose with any Tailwind bg class; `.clay-ring` adds clay depth to ring/outline shapes (drop-shadow)
- **Decorative shapes:** `ClayShapes` sprinkles animated 3D clay geometric shapes across sections (all soft/rounded — float + spin **infinite** via GSAP with relative rotation so they never snap or restart; plain `prefers-reduced-motion` guard, not `gsap.matchMedia`, to avoid ScrollTrigger.refresh() restarting the loops)
- **Glass surfaces:** `.glass-*` utilities — translucent blur on `apple-glass`, solid fallback elsewhere
- **Effects:** soft ambient shadows; scanlines/noise off in light themes
- **Animation:** GSAP with ScrollTrigger — hero timeline on mount, scroll-reveal for section content (badge → heading → cards)

## Work Guidance
- Keep API interaction through the proxy path (`/api/...`) via Axios client in `src/api/client.js`
- New pages go in `src/pages/`, new shared components in `src/components/`, new hooks in `src/hooks/`
- Use `useGSAP` from `@gsap/react` for scroll animations; register `ScrollTrigger` once in `App.jsx`
- All daisyUI component classes must come from daisyUI 5 docs — Tailwind utility overrides for anything custom
- Clay rules (default theme): puffy 3D shadows via `.clay`/`.clay-press`, soft colors, `rounded-*` generously, no harsh borders/outlines
- iOS rules (apple-glass): no neon/high-saturation blocks, no harsh borders, sentence case headings, `rounded-full` for CTAs/pills, glass only where it improves hierarchy/focus/context

## Verification
- `npm run dev` starts Vite dev server
- `npm run build` for production build

## Child DOX Index

| Path | Purpose |
|---|---|
| `src/api/` | Axios instance, auth interceptor, endpoint helpers |
| `src/components/` | Reusable daisyUI + GSAP components (Layout, Sidebar, ChatMessages, Landing sections) |
| `src/icons/` | Curated SVG icon set as React components (fill-based, `currentColor`) |
| `src/hooks/` | Custom React hooks (useMarkdown, useApi) |
| `src/pages/` | Route-level pages (Landing, App, Settings) |
| `src/styles/design-system.css` | Single design-system template — themes, tokens, effects, base |
| `src/theme/` | Theme switching + `useGraphTheme` (React Flow colors from CSS tokens) |
