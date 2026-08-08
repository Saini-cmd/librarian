# frontend/src/theme/

## Purpose
Theme switching and theme-driven runtime values for the frontend. The design-system CSS template in `src/styles/design-system.css` is the source of truth for colors/fonts; this folder exposes the active theme and reads CSS tokens into JS for consumers like React Flow.

## Ownership
- `index.js` — `DEFAULT_THEME` (constant used to pick the active theme; default `clay`), `THEMES` (registry: `clay`, `apple-glass`, `brutalist-dark`, `glass`), `applyTheme(name)` (sets `data-theme` on `<html>` + syncs the meta theme-color from `--ds-theme-color`), `useGraphTheme()` (React hook returning the symbol-graph color set + React Flow `colorMode` resolved from `--ds-graph-*` CSS tokens, recomputed on `data-theme` change)

## Local Contracts
- Active theme is the `data-theme` attribute on `<html>` (set by `applyTheme` in `main.jsx`; `index.html` keeps the no-JS default)
- Switching themes = changing `DEFAULT_THEME` (or calling `applyTheme`); a new theme also needs its `@plugin "daisyui/theme"` block + `[data-theme]` overrides in `design-system.css`
- `useGraphTheme` is the only sanctioned place graph colors come from — components must NOT hardcode the graph palette; JS values mirror the CSS tokens as defensive fallbacks, CSS is authoritative
- All values must stay in sync with `design-system.css` (fonts via `--ds-font-*`, effects via `--ds-glow`/`--ds-glass-*`, graph via `--ds-graph-*`)

## Work Guidance
- Add new graph/token keys here AND in `design-system.css` together
- Keep this module small — no component logic, no API calls

## Verification
- `npm run build`
- Toggle `data-theme` on `<html>` to `brutalist-dark` in devtools; the Graph view colors, glow and React Flow color-mode must change to match

## Child DOX Index
*None*
