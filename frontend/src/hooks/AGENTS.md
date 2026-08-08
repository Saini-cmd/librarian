# frontend/src/hooks/

## Purpose
Custom React hooks shared across components and pages.

## Ownership
- `useMarkdown.js` — Parses raw markdown → sanitized HTML via `marked` + `DOMPurify`
- `useApi.js` — Generic async-call wrapper with `{ data, loading, error, execute, reset }` state
- Note: `useGraphTheme` (theme-driven graph colors) lives in `src/theme/index.js`, not here — it is tightly coupled to the theme registry

## Local Contracts
- Hooks are pure React — no side effects outside of `useEffect` boundaries
- `useMarkdown` handles both sync and async `marked.parse()` output (thenable vs string)
- `useApi` returns a stable `execute` callback via `useCallback`; reset clears all state
- Both hooks clean up on unmount (`mounted` flag in useMarkdown)

## Work Guidance
- New hooks go here, not in components/ or pages/
- Keep hooks focused on a single concern — compose hooks in components when needed

## Verification
- `useMarkdown` used by `src/components/MessageContent.jsx`
- `useApi` available for data-fetching components (not yet used — planned for backend integration)
