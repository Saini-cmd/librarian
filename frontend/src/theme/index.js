import { useEffect, useState } from "react";

export const DEFAULT_THEME = "clay";

export const THEMES = ["clay", "apple-glass", "brutalist-dark", "glass"];

const GRAPH_VARS = {
  kinds: {
    file: "--ds-graph-file",
    class: "--ds-graph-class",
    interface: "--ds-graph-interface",
    impl: "--ds-graph-impl",
    method: "--ds-graph-method",
    function: "--ds-graph-function",
    entity: "--ds-graph-entity",
  },
  edges: {
    defines: "--ds-graph-edge-defines",
    imports: "--ds-graph-edge-imports",
    used_in: "--ds-graph-edge-used_in",
    uses: "--ds-graph-edge-uses",
  },
  background: "--ds-graph-bg",
  grid: "--ds-graph-grid",
  minimap: "--ds-graph-minimap",
  neutral: "--ds-graph-neutral",
  fallback: "--ds-graph-fallback",
  glow: "--ds-glow",
  colorMode: "--ds-graph-color-mode",
};

const GRAPH_FALLBACKS = {
  kinds: {
    file: "#4a7c9b",
    class: "#8b6fb0",
    interface: "#7dd3fc",
    impl: "#c9a06c",
    method: "#b07a8a",
    function: "#5a9e6f",
    entity: "#788291",
  },
  edges: {
    defines: "#fb923c",
    imports: "#facc15",
    used_in: "#2dd4bf",
    uses: "#22c55e",
  },
  background: "#0c0c0c",
  grid: "#262626",
  minimap: "#3f3f46",
  neutral: "#4b4b4f",
  fallback: "#71717a",
  glow: "oklch(68% 0.33 145)",
  colorMode: "dark",
};

function readGraphColors() {
  const styles = getComputedStyle(document.documentElement);
  const read = (name, fallback) =>
    styles.getPropertyValue(name).trim() || fallback;

  return {
    kinds: Object.fromEntries(
      Object.entries(GRAPH_VARS.kinds).map(([key, v]) => [
        key,
        read(v, GRAPH_FALLBACKS.kinds[key]),
      ])
    ),
    edges: Object.fromEntries(
      Object.entries(GRAPH_VARS.edges).map(([key, v]) => [
        key,
        read(v, GRAPH_FALLBACKS.edges[key]),
      ])
    ),
    background: read(GRAPH_VARS.background, GRAPH_FALLBACKS.background),
    grid: read(GRAPH_VARS.grid, GRAPH_FALLBACKS.grid),
    minimap: read(GRAPH_VARS.minimap, GRAPH_FALLBACKS.minimap),
    neutral: read(GRAPH_VARS.neutral, GRAPH_FALLBACKS.neutral),
    fallback: read(GRAPH_VARS.fallback, GRAPH_FALLBACKS.fallback),
    glow: read(GRAPH_VARS.glow, GRAPH_FALLBACKS.glow),
    colorMode: read(GRAPH_VARS.colorMode, GRAPH_FALLBACKS.colorMode),
  };
}

/**
 * Set the active daisyUI theme on <html> and sync the meta
 * theme-color. Reads --ds-theme-color from the applied theme.
 */
export function applyTheme(name) {
  document.documentElement.dataset.theme = name;
  const styles = getComputedStyle(document.documentElement);
  const themeColor = styles.getPropertyValue("--ds-theme-color").trim();
  if (themeColor) {
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", themeColor);
  }
}

/**
 * Resolve the symbol-graph colors from the design-system CSS tokens.
 * Stays in sync with the active theme (re-reads on data-theme change).
 */
export function useGraphTheme() {
  const [colors, setColors] = useState(readGraphColors);

  useEffect(() => {
    const update = () => setColors(readGraphColors());
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => observer.disconnect();
  }, []);

  return colors;
}
