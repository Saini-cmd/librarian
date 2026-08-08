import { memo, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useNodesState,
  useEdgesState,
  useReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import ELK from "elkjs/lib/elk.bundled.js";
import { useGraphTheme } from "../theme";

const EDGE_WIDTH = 1;
const EDGE_OPACITY = 0.55;
const EDGE_OPACITY_DIM = 0.12;
const EDGE_HIGHLIGHT_WIDTH = 2.5;

const NODE_WIDTH = 200;
const NODE_HEIGHT = 52;

// Mirrors Understand-Anything's structural layout: layered ELK ranks +
// orthogonal edge routing minimize crossings and tangles for code graphs.
// aspectRatio ~1.0 (width ~ height) plus tighter rows / taller layer gaps
// keeps the graph from expanding too wide relative to its height.
const ELK_OPTIONS = {
  algorithm: "layered",
  "elk.direction": "DOWN",
  "elk.aspectRatio": "1.0",
  "elk.layered.spacing.nodeNodeBetweenLayers": "150",
  "elk.spacing.nodeNode": "44",
  "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
  "elk.edgeRouting": "ORTHOGONAL",
  "elk.layered.compaction.postCompaction.strategy": "LEFT",
  "elk.padding": "[top=40,left=20,right=20,bottom=20]",
};

const elk = new ELK();

const LAYOUT_CACHE_MAX_NODES = 4000;

function graphFingerprint(nodes, edges) {
  const parts = [];
  for (const n of nodes) parts.push(n.id);
  for (const e of edges) parts.push(`${e.source}>${e.target}${e.edgeType || ""}`);
  parts.sort();
  let h = 0;
  for (const s of parts) {
    for (let j = 0; j < s.length; j += 1) h = (h * 31 + s.charCodeAt(j)) | 0;
  }
  return Math.abs(h).toString(36);
}

function readCachedLayout(key) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeCachedLayout(key, positions) {
  try {
    localStorage.setItem(key, JSON.stringify(positions));
  } catch {
    // storage full or unavailable — ignore
  }
}

function applyPositions(flowNodes, flowEdges, positions, selectedId) {
  const byId = new Map(positions.map((p) => [p.id, p]));
  return flowNodes.map((n) => {
    const p = byId.get(n.id);
    const flags = nodeFlags(n.id, selectedId, flowEdges);
    return {
      ...n,
      position: { x: p ? p.x : 0, y: p ? p.y : 0 },
      data: { ...n.data, ...flags },
    };
  });
}

function kindColor(kind, kinds) {
  return kinds[kind] || kinds.entity;
}

function nodeFlags(id, selectedId, edges) {
  if (!selectedId) return { selected: false, neighbor: false, faded: false };
  if (id === selectedId) return { selected: true, neighbor: false, faded: false };
  const neighbor = edges.some(
    (e) =>
      (e.source === selectedId && e.target === id) ||
      (e.target === selectedId && e.source === id)
  );
  return { selected: false, neighbor, faded: !neighbor };
}

function edgeStyles(ed, selectedId, colors) {
  const highlight = !!selectedId && (ed.source === selectedId || ed.target === selectedId);
  const typeColor = colors.edges[ed.edgeType] || colors.fallback;
  const stroke = selectedId ? (highlight ? typeColor : colors.neutral) : typeColor;
  return {
    ...ed,
    markerEnd: { ...ed.markerEnd, color: stroke },
    style: {
      ...ed.style,
      stroke,
      strokeWidth: highlight ? EDGE_HIGHLIGHT_WIDTH : EDGE_WIDTH,
      opacity: selectedId ? (highlight ? 1 : EDGE_OPACITY_DIM) : EDGE_OPACITY,
    },
  };
}

function nodeMatchesFilters(node, kindFilter, dirFilter) {
  if (kindFilter.size > 0 && !kindFilter.has(node.kind)) return false;
  if (dirFilter) {
    const file = node.file || "";
    if (dirFilter === "(root)") {
      if (file.includes("/")) return false;
    } else if (!file.startsWith(`${dirFilter}/`)) {
      return false;
    }
  }
  return true;
}

const NodeCard = memo(function NodeCard({ data }) {
  const { label, kind, color, selected, neighbor, faded } = data;
  return (
    <div
      className={`relative rounded-xl border border-base-content/10 bg-base-100 px-2.5 py-1.5 shadow-sm transition-[opacity,box-shadow,outline] duration-200 ${
        selected
          ? "outline outline-2 outline-primary glow"
            : faded
              ? "opacity-20"
              : neighbor
                ? "outline outline-1 outline-primary/60 opacity-80"
                : ""
      }`}
      style={{ width: NODE_WIDTH }}
    >
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
      <div
        className="absolute left-0 top-0 h-full w-1 rounded-l-xl"
        style={{ backgroundColor: color }}
      />
      <div className="pl-1.5 font-mono text-[11px] leading-tight text-base-content truncate" title={label}>
        {label}
      </div>
      <div
        className="pl-1.5 font-mono text-[9px] uppercase tracking-widest"
        style={{ color }}
      >
        {kind}
      </div>
    </div>
  );
});

const nodeTypes = { ua: NodeCard };

export default function SymbolGraph2DView({ graph, selectedId, onSelect }) {
  return (
    <ReactFlowProvider>
      <GraphFlow graph={graph} selectedId={selectedId} onSelect={onSelect} />
    </ReactFlowProvider>
  );
}

function GraphFlow({ graph, selectedId, onSelect }) {
  const rf = useReactFlow();
  const graphTheme = useGraphTheme();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [layouting, setLayouting] = useState(false);
  const selectedIdRef = useRef(selectedId);
  selectedIdRef.current = selectedId;
  const [kindFilter, setKindFilter] = useState(() => new Set());
  const [dirFilter, setDirFilter] = useState("");
  const filtersActive = kindFilter.size > 0 || dirFilter !== "";
  const [filterOpen, setFilterOpen] = useState(false);
  const filterRef = useRef(null);

  const base = useMemo(() => {
    const gNodes = graph?.nodes ?? [];
    const gEdges = graph?.edges ?? [];
    const flowNodes = gNodes.map((n) => ({
      id: n.id,
      type: "ua",
      position: { x: 0, y: 0 },
      data: {
        ...n,
        label: n.label,
        kind: n.kind,
        color: kindColor(n.kind, graphTheme.kinds),
        selected: false,
        neighbor: false,
        faded: false,
      },
    }));
    const flowEdges = gEdges.map((e, i) => {
      const stroke = graphTheme.edges[e.type] || graphTheme.fallback;
      return {
        id: `e${i}`,
        source: e.source,
        target: e.target,
        edgeType: e.type,
        type: "step",
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 12,
          height: 12,
          color: stroke,
        },
        style: {
          stroke,
          strokeWidth: EDGE_WIDTH,
          opacity: EDGE_OPACITY,
        },
      };
    });
    return { flowNodes, flowEdges };
  }, [graph, graphTheme]);

  const kinds = useMemo(() => {
    const set = new Set();
    for (const n of graph?.nodes ?? []) if (n.kind) set.add(n.kind);
    return [...set].sort();
  }, [graph]);

  const dirs = useMemo(() => {
    const set = new Set();
    for (const n of graph?.nodes ?? []) {
      const file = n.file || "";
      if (!file) continue;
      if (!file.includes("/")) {
        set.add("(root)");
        continue;
      }
      const parts = file.split("/");
      for (let i = 1; i < parts.length; i += 1) {
        set.add(parts.slice(0, i).join("/"));
      }
    }
    return [...set].sort();
  }, [graph]);

  const matchSet = useMemo(() => {
    if (!filtersActive) return null;
    const ids = new Set();
    for (const n of graph?.nodes ?? []) {
      if (nodeMatchesFilters(n, kindFilter, dirFilter)) ids.add(n.id);
    }
    return ids;
  }, [graph, kindFilter, dirFilter, filtersActive]);

  const filteredBase = useMemo(() => {
    if (!matchSet) return base;
    const flowNodes = base.flowNodes.filter((n) => matchSet.has(n.id));
    const flowEdges = base.flowEdges.filter(
      (e) => matchSet.has(e.source) && matchSet.has(e.target)
    );
    return { flowNodes, flowEdges };
  }, [base, matchSet]);

  const filterCount = kindFilter.size + (dirFilter ? 1 : 0);
  const matchCount = filteredBase.flowNodes.length;
  const totalCount = base.flowNodes.length;
  const filteredEmpty = filtersActive && matchCount === 0;

  function toggleKind(kind) {
    setKindFilter((prev) => {
      const next = new Set(prev);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });
  }

  function clearFilters() {
    setKindFilter(new Set());
    setDirFilter("");
  }

  useEffect(() => {
    setKindFilter(new Set());
    setDirFilter("");
  }, [graph?.repo]);

  useEffect(() => {
    if (!filterOpen) return undefined;
    const onPointerDown = (e) => {
      if (filterRef.current && !filterRef.current.contains(e.target)) setFilterOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [filterOpen]);

  useEffect(() => {
    if (!filteredBase.flowNodes.length) {
      setNodes([]);
      setEdges([]);
      setLayouting(false);
      return undefined;
    }

    const repo = graph?.repo || "";
    const cacheKey =
      repo && !filtersActive
        ? `ua-layout:v2:${repo}:${graphFingerprint(filteredBase.flowNodes, filteredBase.flowEdges)}`
        : "";
    const cacheable = cacheKey && filteredBase.flowNodes.length <= LAYOUT_CACHE_MAX_NODES;

    const cached = cacheable ? readCachedLayout(cacheKey) : null;
    if (cached) {
      setLayouting(false);
      setNodes(applyPositions(filteredBase.flowNodes, filteredBase.flowEdges, cached, selectedIdRef.current));
      setEdges(filteredBase.flowEdges.map((ed) => edgeStyles(ed, selectedIdRef.current, graphTheme)));
      return undefined;
    }

    let cancelled = false;
    // Structural edges only drive the layered ranks (like their dashboard):
    // defines + imports give a clean hierarchy; dense uses/used_in edges are
    // rendered on top but don't influence placement.
    const layoutEdges = filteredBase.flowEdges.filter(
      (e) => e.edgeType === "defines" || e.edgeType === "imports"
    );
    const input = {
      id: "root",
      layoutOptions: ELK_OPTIONS,
      children: filteredBase.flowNodes.map((n) => ({
        id: n.id,
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
      })),
      edges: layoutEdges.map((e) => ({ id: e.id, sources: [e.source], targets: [e.target] })),
    };

    setLayouting(true);
    elk
      .layout(input)
      .then((pos) => {
        if (cancelled) return;
        const byId = new Map(pos.children.map((c) => [c.id, c]));
        const placed = filteredBase.flowNodes.map((n) => {
          const p = byId.get(n.id);
          const flags = nodeFlags(n.id, selectedIdRef.current, filteredBase.flowEdges);
          return {
            ...n,
            position: { x: p ? p.x : 0, y: p ? p.y : 0 },
            data: { ...n.data, ...flags },
          };
        });
        if (cacheable) {
          writeCachedLayout(
            cacheKey,
            placed.map((n) => ({ id: n.id, x: n.position.x, y: n.position.y }))
          );
        }
        setNodes(placed);
        setEdges(filteredBase.flowEdges.map((ed) => edgeStyles(ed, selectedIdRef.current, graphTheme)));
        setLayouting(false);
      })
      .catch(() => {
        if (cancelled) return;
        setLayouting(false);
      });

    return () => {
      cancelled = true;
    };
  }, [filteredBase, filtersActive, graph, graphTheme, setEdges, setNodes]);

  useEffect(() => {
    setNodes((nds) =>
      nds.map((n) => ({
        ...n,
        data: { ...n.data, ...nodeFlags(n.id, selectedId, filteredBase.flowEdges) },
      }))
    );
    setEdges((eds) => eds.map((ed) => edgeStyles(ed, selectedId, graphTheme)));
  }, [selectedId, filteredBase, graphTheme, setNodes, setEdges]);

  useEffect(() => {
    if (nodes.length) {
      requestAnimationFrame(() => rf.fitView({ padding: 0.15, duration: 400 }));
    }
  }, [nodes.length, rf]);

  return (
    <div className="absolute inset-0 graph-surface">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        colorMode={graphTheme.colorMode}
        minZoom={0.05}
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_, node) => node.data && onSelect(node.data)}
        onPaneClick={() => onSelect(null)}
      >
        <Background color={graphTheme.grid} gap={28} size={1} />
        <Controls showInteractive={false} />
        <MiniMap nodeColor={(n) => n.data?.color || graphTheme.minimap} pannable zoomable />
      </ReactFlow>

      {layouting && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-base-100/60">
          <span className="loading loading-dots loading-lg" />
        </div>
      )}

      {filteredEmpty && (
        <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center">
          <span className="rounded-xl border border-base-content/10 bg-base-100/80 px-4 py-2 font-mono text-[11px] uppercase tracking-widest text-base-content/60 backdrop-blur-md">
            No nodes match the current filters
          </span>
        </div>
      )}

      <div className="absolute top-2 right-2 z-30 flex items-center gap-1">
        {filtersActive && (
          <button
            className="btn btn-circle btn-sm btn-ghost border border-base-content/10"
            title="Reset filters"
            onClick={clearFilters}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 20 20"
              fill="currentColor"
              className="h-4 w-4"
            >
              <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
            </svg>
          </button>
        )}

        <details
          ref={filterRef}
          className="dropdown dropdown-end"
          open={filterOpen}
          onToggle={(e) => setFilterOpen(e.target.open)}
        >
          <summary className="btn btn-sm btn-ghost gap-1 border border-base-content/10">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 20 20"
              fill="currentColor"
              className="h-4 w-4"
            >
              <path
                fillRule="evenodd"
                d="M2.628 1.601C5.028 1.206 7.49 1 10 1s4.973.206 7.372.601a.75.75 0 0 1 .628.74v2.288a2.25 2.25 0 0 1-.659 1.59l-4.682 4.683a2.25 2.25 0 0 0-.659 1.59v3.037c0 .684-.31 1.33-.844 1.757l-1.937 1.55A.75.75 0 0 1 8 18.25v-5.757a2.25 2.25 0 0 0-.659-1.591L2.659 6.22A2.25 2.25 0 0 1 2 4.629V2.34a.75.75 0 0 1 .628-.74Z"
                clipRule="evenodd"
              />
            </svg>
            {filtersActive && (
              <span className="badge badge-primary badge-xs">{filterCount}</span>
            )}
          </summary>
          <div className="dropdown-content z-30 mt-2 w-64 max-h-[70vh] overflow-y-auto rounded-xl border border-base-content/10 bg-base-100 p-3 shadow-xl backdrop-blur-md">
            <div className="space-y-3">
              <section className="space-y-1">
                <div className="font-mono text-[9px] uppercase tracking-widest text-base-content/40">
                  Node type
                </div>
                <div className="grid grid-cols-2 gap-1">
                  {kinds.map((kind) => (
                    <label
                      key={kind}
                      className="flex cursor-pointer items-center gap-1.5 font-mono text-[11px] text-base-content"
                    >
                      <input
                        type="checkbox"
                        className="checkbox checkbox-primary checkbox-xs"
                        checked={kindFilter.has(kind)}
                        onChange={() => toggleKind(kind)}
                      />
                      <span
                        className="h-2 w-2 rounded-sm"
                        style={{ backgroundColor: kindColor(kind, graphTheme.kinds) }}
                      />
                      {kind}
                    </label>
                  ))}
                </div>
              </section>

              <section className="space-y-1">
                <div className="font-mono text-[9px] uppercase tracking-widest text-base-content/40">
                  Directory
                </div>
                <select
                  className="select select-sm select-bordered w-full font-mono text-[11px]"
                  value={dirFilter}
                  onChange={(e) => setDirFilter(e.target.value)}
                >
                  <option value="">All directories</option>
                  {dirs.map((dir) => {
                    const depth = dir.split("/").length - 1;
                    const indent = dirFilter === dir ? "" : "\u00A0\u00A0".repeat(depth);
                    return (
                      <option key={dir} value={dir}>
                        {dir === "(root)" ? "(root)" : `${indent}${dir}`}
                      </option>
                    );
                  })}
                </select>
              </section>

              <div className="flex items-center justify-between border-t border-base-content/10 pt-2">
                <span className="font-mono text-[9px] uppercase tracking-widest text-base-content/50">
                  {filtersActive
                    ? `${matchCount} of ${totalCount} nodes`
                    : `${totalCount} nodes`}
                </span>
                <button className="btn btn-xs btn-ghost" onClick={clearFilters}>
                  Clear all
                </button>
              </div>
            </div>
          </div>
        </details>
      </div>

      <div className="absolute top-2 left-2 z-10 space-y-1 rounded-xl border border-base-content/10 bg-base-100/80 backdrop-blur-md px-2.5 py-1.5 font-mono text-[9px] uppercase tracking-widest text-base-content/70">
        <div className="text-[8px] text-primary">Edges</div>
        <div className="flex flex-wrap gap-x-3 gap-y-1">
          {Object.entries(graphTheme.edges).map(([type, color]) => (
            <span key={type} className="inline-flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm" style={{ backgroundColor: color }} />
              {type}
            </span>
          ))}
        </div>
        <div className="pt-1 text-[8px] text-base-content/40">Nodes</div>
        <div className="flex flex-wrap gap-x-3 gap-y-1">
          {Object.entries(graphTheme.kinds).map(([kind, color]) => (
            <span key={kind} className="inline-flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm" style={{ backgroundColor: color }} />
              {kind}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
