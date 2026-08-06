# frontend/src/components/

## Purpose
Reusable UI components for landing page and app screens. Built with daisyUI 5 class names and Tailwind CSS 4 utilities, following the brutalist design system.

## Ownership
- `Layout.jsx` — App shell: daisyUI drawer with sidebar (LG always open) + content area
- `Sidebar.jsx` — Conversation list, single `+ Ingest New Repo` action button (always), settings/sign-out nav
- `SymbolGraphView.jsx` — Repo symbol graph (**2D only** — the 3D view was removed): renders `SymbolGraph2DView` plus the shared detail panel. Clicking a file node streams its stored summary (typewriter) + lists its entities; clicking an entity node shows its code snippet; background click clears the panel. Loading/error/empty states handled here
- `SymbolGraph2DView.jsx` — 2D graph via `@xyflow/react` (React Flow) + `elkjs`, mirroring the Understand-Anything dashboard design: **kind-coded card nodes** (`KIND_COLORS`: file blue, class purple, interface sky, impl gold, method pink, function green, entity slate) with a colored left bar + mono label + kind tag; **ELK layered layout** (`ELK_OPTIONS`: `algorithm: layered`, direction DOWN, `edgeRouting: ORTHOGONAL`, `LAYER_SWEEP` crossing minimization — the anti-tangle approach their structural view uses) computed async per repo, fed with **structural edges only** (`defines` + `imports`; dense `uses`/`used_in` are rendered on top but don't influence placement); **positions are cached in localStorage** (`ua-layout:{repo}:{fingerprint}`) so repeat loads skip `elk.layout()` entirely (capped at `LAYOUT_CACHE_MAX_NODES`), then `fitView`; **step edges colored by edge type** (`EDGE_COLORS`: defines orange, imports yellow, used_in teal, uses green) with uniform width/opacity and `MarkerType.ArrowClosed` arrowheads (same color) pointing at the edge target — for `defines` that's the parent file; **selection focus** dims unrelated nodes to `opacity-20` and unrelated edges to `EDGE_OPACITY_DIM` + a **neutral grey stroke** (their type color is dropped) while **highlighting the selected node's incident edges** (thicker `EDGE_HIGHLIGHT_WIDTH`, full opacity, keeping their own type color) and keeping direct neighbors at `opacity-80`; **selection fade** — the selected node gets a `primary` ring + glow while neighbors get a thin ring and everything else fades to `opacity-20`; legend overlay (bottom-left) with **language-neutral Edges section** (defines/imports/used_in/uses colors) above a Nodes section, dark React Flow theme (`colorMode="dark"`), MiniMap + zoom controls, `fitView` on load. Node click → `onSelect` (shared detail panel), pane click clears. NOTE: custom node `data` carries the raw backend node so the shared panel works unchanged
- `MessageContent.jsx` — Markdown-rendered assistant messages vs plain user messages; assistant content wrapped in `prose prose-invert prose-sm max-w-none` (Tailwind typography plugin) for readable paragraphs/headings/lists/code/tables
- `RepoInput.jsx` — GitHub URL input form with join-group button
- `ProgressBar.jsx` — Pipeline progress bar + step indicators (stages: ingest → scan → chunk → embed → ready)
- `ChatMessages.jsx` — Scrollable message list (`flex-1 min-h-0` so it scrolls internally within the fixed-height app shell, growing upward during streaming), auto-scroll, empty state (centered "Ready to chat" label shown when there are no messages; disappears once any message is sent). Typing/loading indicator renders inside the empty assistant placeholder bubble (no separate loading bubble)
- `LandingHero.jsx` — Full-viewport hero with GSAP entrance timeline (badge → title → AI → subtitle → CTA)
- `LandingFeatures.jsx` — Feature grid (2x2) with GSAP scroll-reveal (badge → heading → cards)
- `LandingHowItWorks.jsx` — 3-step workflow with GSAP scroll-reveal (badge → heading → cards)
- `LandingFooter.jsx` — Footer with GSAP fade-in on scroll

## Local Contracts
- All components use daisyUI class names (`btn`, `input`, `chat`, `menu`, `drawer`, etc.) — no hand-written CSS
- Brutalist constraints: zero border-radius, 2px borders, uppercase headings, monospace for data
- GSAP animations registered via `ScrollTrigger.create()` in `useLayoutEffect` with StrictMode guard
- Landing page components accept no props — self-contained with Clerk hooks and GSAP timelines
- App components (Layout, Sidebar, ChatMessages, etc.) receive data via props from `AppPage`

## Work Guidance
- New shared UI elements go here, not in pages/
- Use daisyUI component classes first, Tailwind utilities for overrides, `!` suffix only as last resort
- Scroll-triggered animations use `gsap.context()` + `ctx.revert()` for proper StrictMode cleanup
- Keep components focused — if a component needs significant state, consider extracting to a hook

## Verification
- All components rendered on either `/` (Landing) or `/app` (App) routes
- Build verified with `npm run build`
