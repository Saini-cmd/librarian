# frontend/src/icons/

## Purpose
Curated SVG icon set exposed as React components. Icons render with `currentColor` (fill-based by default; `send` is stroke-based), so they inherit color from their context (daisyUI semantic classes or `--ds-*` tokens) — never hardcoded.

## Ownership
- `Icon.jsx` — name→`{ viewBox, paths[], stroke? }` registry + default `<Icon name="…" />` component and named exports (`IconAdd`, `IconBack`, `IconChat`, `IconChevronsLeft`, `IconClose`, `IconExit`, `IconFilter`, `IconGraph`, `IconLanguage`, `IconMenu`, `IconPipeline`, `IconSave`, `IconSearch`, `IconSend`, `IconSettings`, `IconStream`, `IconSync`, `IconTrash`, `IconWarning`)

## Local Contracts
- Default sizing via `className` (e.g. `w-4 h-4`); no intrinsic width/height
- Root `<svg>` sets `fill="currentColor"` (fill-based icons) or `fill="none"` + `stroke="currentColor"` (stroke-based icons with `icon.stroke = { width, cap, join }`), `aria-hidden="true"`, `focusable="false"`
- Each icon keeps its native `viewBox` (`0 0 24 24` for all except `sync`, which is `0 0 48 48`)
- Source SVGs are normalized (width/height, `id`/`data-name`, `<title>`, empty `<rect>` wrappers, hardcoded fill/stroke stripped) — do not reintroduce them

## Work Guidance
- Add new icons here (registry entry + named export), not as raw `.svg` asset files — raw files cannot be `currentColor`-tinted and would break the themeable design system
- Prefer the named exports in components; use the default `Icon name` form only for dynamic names

## Verification
- All icon names resolve to a non-null `<svg>` (unknown names render null)
- Build verified with `npm run build`

## Child DOX Index
*None*
