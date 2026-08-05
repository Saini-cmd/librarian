# frontend/src/components/

## Purpose
Reusable UI components for landing page and app screens. Built with daisyUI 5 class names and Tailwind CSS 4 utilities, following the brutalist design system.

## Ownership
- `Layout.jsx` — App shell: daisyUI drawer with sidebar (LG always open) + content area
- `Sidebar.jsx` — Conversation list, new-chat button, settings/sign-out nav
- `MessageContent.jsx` — Markdown-rendered assistant messages vs plain user messages
- `RepoInput.jsx` — GitHub URL input form with join-group button
- `ProgressBar.jsx` — Pipeline progress bar + step indicators (stages: ingest → scan → chunk → embed → ready)
- `ChatMessages.jsx` — Scrollable message list with auto-scroll, typing indicator, empty state
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
