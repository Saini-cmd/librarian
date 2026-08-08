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

  useEffect(() => {
    if (!base.flowNodes.length) {
      setNodes([]);
      setEdges([]);
      return undefined;
    }

    const repo = graph?.repo || "";
    const cacheKey = repo ? `ua-layout:v2:${repo}:${graphFingerprint(base.flowNodes, base.flowEdges)}` : "";
    const cacheable = cacheKey && base.flowNodes.length <= LAYOUT_CACHE_MAX_NODES;

    const cached = cacheable ? readCachedLayout(cacheKey) : null;
    if (cached) {
      setNodes(applyPositions(base.flowNodes, base.flowEdges, cached, selectedIdRef.current));
      setEdges(base.flowEdges.map((ed) => edgeStyles(ed, selectedIdRef.current, graphTheme)));
      return undefined;
    }

    let cancelled = false;
    // Structural edges only drive the layered ranks (like their dashboard):
    // defines + imports give a clean hierarchy; dense uses/used_in edges are
    // rendered on top but don't influence placement.
    const layoutEdges = base.flowEdges.filter(
      (e) => e.edgeType === "defines" || e.edgeType === "imports"
    );
    const input = {
      id: "root",
      layoutOptions: ELK_OPTIONS,
      children: base.flowNodes.map((n) => ({
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
        const placed = base.flowNodes.map((n) => {
          const p = byId.get(n.id);
          const flags = nodeFlags(n.id, selectedIdRef.current, base.flowEdges);
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
        setEdges(base.flowEdges.map((ed) => edgeStyles(ed, selectedIdRef.current, graphTheme)));
        setLayouting(false);
      })
      .catch(() => {
        if (cancelled) return;
        setLayouting(false);
      });

    return () => {
      cancelled = true;
    };
  }, [base, graph, graphTheme, setEdges, setNodes]);

  useEffect(() => {
    setNodes((nds) =>
      nds.map((n) => ({
        ...n,
        data: { ...n.data, ...nodeFlags(n.id, selectedId, base.flowEdges) },
      }))
    );
    setEdges((eds) => eds.map((ed) => edgeStyles(ed, selectedId, graphTheme)));
  }, [selectedId, base, graphTheme, setNodes, setEdges]);

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
