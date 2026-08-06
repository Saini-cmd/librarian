import { useEffect, useMemo, useRef, useState } from "react";
import { ReactFlow, Background, Controls, MarkerType, Handle, Position } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCollide,
  forceRadial,
  forceCenter,
} from "d3-force";

import { getFileSummary } from "../api/client";
import MessageContent from "./MessageContent";

const EDGE_STYLES = {
  defines: { stroke: "#71717a", strokeWidth: 1, strokeDasharray: "2 3", opacity: 0.55 },
  used_in: { stroke: "#22c55e", strokeWidth: 1.5, strokeDasharray: "6 4" },
  uses: { stroke: "#22c55e", strokeWidth: 1.5 },
};

const KIND_STYLES = {
  class: "bg-primary/20 border-primary/40",
  interface: "bg-accent/20 border-accent/40",
  impl: "bg-base-300 border-base-300",
  method: "bg-base-300 border-base-300",
  function: "bg-base-300 border-base-300",
  entity: "bg-base-300 border-base-300",
};

const LABEL_RADIUS = 72;
const INTRA_GAP = 10;
const FILE_GAP = 24;
const MAX_TICKS = 250;
const LAYOUT_SEED = 42;

function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const HANDLE_STYLE = {
  opacity: 0,
  width: 1,
  height: 1,
  border: "none",
  background: "transparent",
};

function entityDiameter(label) {
  const len = label ? label.length : 4;
  return Math.min(150, Math.max(56, len * 7 + 28));
}

function FileNode({ data, selected, width, height }) {
  const w = width || 220;
  const h = height || 220;
  return (
    <div
      className={`absolute rounded-full border-2 border-dashed flex items-center justify-center bg-transparent ${
        selected ? "border-primary" : "border-base-300/60"
      }`}
      style={{ width: w, height: h, borderRadius: "50%" }}
    >
      <Handle type="target" position={Position.Top} style={HANDLE_STYLE} />
      <Handle type="source" position={Position.Bottom} style={HANDLE_STYLE} />
      <div className="text-center px-2 pointer-events-none">
        <div className="font-mono text-[9px] uppercase tracking-widest text-base-content/40">
          FILE
        </div>
        <div
          className="font-mono text-xs font-bold break-all max-w-[130px] truncate"
          title={data.label}
        >
          {data.label}
        </div>
        <div className="font-mono text-[9px] text-base-content/40">
          {data.entityCount} {data.entityCount === 1 ? "entity" : "entities"}
        </div>
      </div>
    </div>
  );
}

function EntityNode({ data, selected }) {
  return (
    <div
      className={`absolute rounded-full border-2 flex flex-col items-center justify-center text-center px-1 overflow-hidden ${
        KIND_STYLES[data.kind] || "bg-base-300 border-base-300"
      } ${selected ? "border-primary" : ""}`}
      style={{ width: "100%", height: "100%", borderRadius: "50%" }}
    >
      <Handle type="target" position={Position.Top} style={HANDLE_STYLE} />
      <Handle type="source" position={Position.Bottom} style={HANDLE_STYLE} />
      <div className="font-mono text-[7px] uppercase tracking-widest text-base-content/50">
        {data.kind}
      </div>
      <div
        className="font-mono text-[9px] font-bold leading-tight break-all max-h-8 overflow-hidden w-full"
        title={data.label}
      >
        {data.label}
      </div>
    </div>
  );
}

function layoutEntities(fileKey, entities, diameters, intraLinks, seed) {
  const nodes = entities.map((e, i) => ({
    id: e.id,
    radius: diameters[i] / 2,
    x: 0,
    y: 0,
    vx: 0,
    vy: 0,
  }));
  const radialTarget = (n) => LABEL_RADIUS + n.radius + 8;
  nodes.forEach((n, i) => {
    const a = (2 * Math.PI * i) / nodes.length - Math.PI / 2;
    n.x = Math.cos(a) * radialTarget(n);
    n.y = Math.sin(a) * radialTarget(n);
  });

  const links = intraLinks
    .map(([s, t]) => {
      const sNode = nodes.find((n) => n.id === s);
      const tNode = nodes.find((n) => n.id === t);
      if (!sNode || !tNode) return null;
      return {
        source: sNode,
        target: tNode,
        distance: sNode.radius + tNode.radius + INTRA_GAP,
      };
    })
    .filter(Boolean);

  const sim = forceSimulation(nodes)
    .force("link", forceLink(links).id((d) => d.id).strength(0.6))
    .force("charge", forceManyBody().strength(-140))
    .force("collide", forceCollide().radius((d) => d.radius + INTRA_GAP))
    .force("radial", forceRadial(radialTarget, 0, 0).strength(0.35))
    .stop();
  sim.randomSource(mulberry32(seed + (entities.length || 1)));
  nodes.forEach((n) => {
    n.vx = 0;
    n.vy = 0;
  });
  for (let i = 0; i < MAX_TICKS; i += 1) sim.tick();

  const positions = nodes.map((n, i) => ({
    x: n.x,
    y: n.y,
    diameter: diameters[i],
  }));
  let maxDist = 0;
  nodes.forEach((n) => {
    maxDist = Math.max(maxDist, Math.hypot(n.x, n.y) + n.radius);
  });
  const parentRadius = Math.max(maxDist + 16, LABEL_RADIUS + 40);
  return { positions, parentRadius };
}

function layoutFiles(files, fileEdges, seed) {
  if (!files.length) return [];
  const nodes = files.map((f) => ({
    id: f.fileNode.id,
    radius: f.parentRadius,
    x: 0,
    y: 0,
    vx: 0,
    vy: 0,
  }));
  nodes.forEach((n, i) => {
    const a = (2 * Math.PI * i) / nodes.length - Math.PI / 2;
    n.x = Math.cos(a) * 400;
    n.y = Math.sin(a) * 400;
  });

  const links = fileEdges
    .map(({ source, target, weight }) => {
      const sNode = nodes.find((n) => n.id === source);
      const tNode = nodes.find((n) => n.id === target);
      if (!sNode || !tNode) return null;
      const base = sNode.radius + tNode.radius + FILE_GAP + 20;
      const distance = Math.max(base - weight * 10, sNode.radius + tNode.radius + 8);
      return { source: sNode, target: tNode, distance, strength: 0.5 };
    })
    .filter(Boolean);

  const sim = forceSimulation(nodes)
    .force("link", forceLink(links).id((d) => d.id))
    .force("charge", forceManyBody().strength(-120))
    .force("collide", forceCollide().radius((d) => d.radius + FILE_GAP))
    .force("center", forceCenter(0, 0))
    .stop();
  sim.randomSource(mulberry32(seed));
  nodes.forEach((n) => {
    n.vx = 0;
    n.vy = 0;
  });
  for (let i = 0; i < MAX_TICKS; i += 1) sim.tick();

  return nodes.map((n) => ({
    id: n.id,
    cx: n.x,
    cy: n.y,
    size: 2 * n.radius,
  }));
}

function layoutGraph(graph) {
  if (!graph) return { nodes: [], edges: [] };

  const entitiesByFile = {};
  const entityById = {};
  const fileById = {};
  graph.nodes.forEach((n) => {
    if (n.kind === "file") {
      fileById[n.id] = n;
    } else {
      (entitiesByFile[n.file] = entitiesByFile[n.file] || []).push(n);
      entityById[n.id] = n;
    }
  });
  const fileNodes = graph.nodes.filter((n) => n.kind === "file");

  const intraLinksByFile = {};
  const crossWeight = {};
  graph.edges.forEach((e) => {
    if (e.type === "defines" || e.source === e.target) return;
    const s = entityById[e.source] || null;
    const t = entityById[e.target] || null;
    let fa = s ? s.file : null;
    let fb = t ? t.file : null;
    if (s && fileById[e.target]) fb = fileById[e.target].file;
    if (t && fileById[e.source]) fa = fileById[e.source].file;
    if (!fa || !fb) return;
    if (fa === fb) {
      if (s && t) {
        (intraLinksByFile[fa] = intraLinksByFile[fa] || []).push([s.id, t.id]);
      }
      return;
    }
    const key = [fa, fb].sort().join("::");
    crossWeight[key] = (crossWeight[key] || 0) + 1;
  });

  const files = fileNodes.map((fileNode, idx) => {
    const entities = entitiesByFile[fileNode.file] || [];
    const diameters = entities.map((e) => entityDiameter(e.label));
    const intraLinks = intraLinksByFile[fileNode.file] || [];
    const { positions, parentRadius } = layoutEntities(
      fileNode.id,
      entities,
      diameters,
      intraLinks,
      LAYOUT_SEED + idx * 7
    );
    return { fileNode, entities, positions, parentRadius };
  });

  const fileEdges = Object.entries(crossWeight).map(([key, weight]) => {
    const [a, b] = key.split("::");
    return { source: `file:${a}`, target: `file:${b}`, weight };
  });
  const arranged = layoutFiles(files, fileEdges, LAYOUT_SEED);

  const centerByFile = {};
  arranged.forEach((a) => {
    centerByFile[a.id] = { cx: a.cx, cy: a.cy, size: a.size };
  });

  const nodes = [];

  files.forEach((f) => {
    const center = centerByFile[f.fileNode.id] || { cx: 0, cy: 0, size: f.parentRadius * 2 };
    nodes.push({
      id: f.fileNode.id,
      type: "fileNode",
      position: { x: center.cx - center.size / 2, y: center.cy - center.size / 2 },
      width: center.size,
      height: center.size,
      data: { ...f.fileNode, entityCount: f.entities.length },
    });
  });

  files.forEach((f) => {
    const center = centerByFile[f.fileNode.id] || { cx: 0, cy: 0 };
    f.entities.forEach((entity, idx) => {
      const pos = f.positions[idx];
      const d = pos.diameter;
      nodes.push({
        id: entity.id,
        type: "entityNode",
        position: {
          x: center.cx + pos.x - d / 2,
          y: center.cy + pos.y - d / 2,
        },
        width: d,
        height: d,
        data: entity,
      });
    });
  });

  const nodeIds = new Set(nodes.map((n) => n.id));
  const edges = graph.edges
    .filter(
      (e) =>
        e.source !== e.target &&
        nodeIds.has(e.source) &&
        nodeIds.has(e.target)
    )
    .map((e, i) => ({
      id: `e${i}`,
      source: e.source,
      target: e.target,
      style: EDGE_STYLES[e.type] || EDGE_STYLES.uses,
      markerEnd:
        e.type === "defines"
          ? undefined
          : { type: MarkerType.ArrowClosed, color: "#22c55e" },
    }));

  return { nodes, edges };
}

export default function SymbolGraphView({ graph, loading, error }) {
  const { nodes, edges } = useMemo(() => {
    try {
      return layoutGraph(graph);
    } catch {
      return { nodes: [], edges: [] };
    }
  }, [graph]);
  const layoutFailed = !nodes.length && !edges.length && graph && graph.nodes.length > 0;
  const noReferences =
    !loading && !error && !layoutFailed && graph && nodes.length > 0 && edges.length === 0;
  const nodeTypes = useMemo(
    () => ({ fileNode: FileNode, entityNode: EntityNode }),
    []
  );

  const [selected, setSelected] = useState(null);
  const [summary, setSummary] = useState("");
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState("");
  const typeRef = useRef(null);
  const fetchToken = useRef(0);

  useEffect(() => {
    if (typeRef.current) clearInterval(typeRef.current);
    setSelected(null);
    setSummary("");
    setSummaryLoading(false);
    setSummaryError("");
  }, [graph?.repo]);

  useEffect(() => () => {
    if (typeRef.current) clearInterval(typeRef.current);
  }, []);

  function streamText(text) {
    if (typeRef.current) clearInterval(typeRef.current);
    let i = 0;
    setSummary("");
    typeRef.current = setInterval(() => {
      i += 1;
      setSummary(text.slice(0, i));
      if (i >= text.length) {
        clearInterval(typeRef.current);
        typeRef.current = null;
      }
    }, 10);
  }

  async function handleNodeClick(evt, node) {
    const data = node.data;
    const token = ++fetchToken.current;
    if (typeRef.current) clearInterval(typeRef.current);
    setSelected(data);
    setSummary("");
    setSummaryError("");
    setSummaryLoading(false);

    if (data.kind !== "file") return;

    setSummaryLoading(true);
    try {
      const res = await getFileSummary(graph.repo, data.file);
      if (token !== fetchToken.current) return;
      setSummaryLoading(false);
      streamText(res.summary);
    } catch {
      if (token !== fetchToken.current) return;
      setSummaryLoading(false);
      setSummaryError("No summary for this file");
    }
  }

  const fileEntities = useMemo(() => {
    if (!graph || !selected || selected.kind !== "file") return [];
    return graph.nodes.filter((n) => n.kind !== "file" && n.file === selected.file);
  }, [graph, selected]);

  return (
    <div className="flex-1 min-h-0 flex">
      <div className="flex-1 min-w-0 relative">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <span className="loading loading-dots loading-lg" />
          </div>
        ) : error ? (
          <div className="flex items-center justify-center h-full text-error font-mono text-sm uppercase">
            {error}
          </div>
        ) : layoutFailed ? (
          <div className="flex items-center justify-center h-full text-error font-mono text-xs uppercase tracking-widest">
            Could not render graph
          </div>
        ) : !graph || nodes.length === 0 ? (
          <div className="flex items-center justify-center h-full text-base-content/40 font-mono text-xs uppercase tracking-widest">
            No symbol data for this repo
          </div>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodeClick={handleNodeClick}
            fitView
            fitViewOptions={{ padding: 0.15 }}
            minZoom={0.05}
            nodesConnectable={false}
            nodesDraggable={false}
            nodesFocusable={false}
          >
            <Background gap={24} color="#2a2a2a" />
            <Controls position="bottom-left" />
          </ReactFlow>
        )}

        {noReferences && (
          <div className="absolute top-3 left-1/2 -translate-x-1/2 px-3 py-1 border-2 border-base-300 bg-base-200 text-[10px] font-mono uppercase tracking-widest text-base-content/50 pointer-events-none">
            No references found for this repo
          </div>
        )}
      </div>

      {selected && (
        <aside className="w-96 shrink-0 border-l-2 border-base-300 bg-base-200 flex flex-col min-h-0">
          <div className="p-4 border-b-2 border-base-300 space-y-1">
            <div className="font-mono text-[10px] uppercase tracking-widest text-primary">
              {selected.kind}
            </div>
            <h3 className="font-bold text-sm uppercase truncate">{selected.label}</h3>
            <div className="font-mono text-[10px] text-base-content/50 truncate">
              {selected.file}
              {selected.start_line
                ? `:${selected.start_line}-${selected.end_line}`
                : ""}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {selected.kind === "file" ? (
              <>
                <section className="space-y-2">
                  <h4 className="font-mono text-[10px] uppercase tracking-widest text-base-content/40">
                    File Summary
                  </h4>
                  {summaryLoading ? (
                    <span className="loading loading-dots loading-sm" />
                  ) : summaryError ? (
                    <p className="text-xs font-mono text-base-content/50">
                      {summaryError}
                    </p>
                  ) : (
                    <div className="text-sm leading-relaxed">
                      <MessageContent role="assistant" content={summary} />
                    </div>
                  )}
                </section>

                {fileEntities.length > 0 && (
                  <section className="space-y-2">
                    <h4 className="font-mono text-[10px] uppercase tracking-widest text-base-content/40">
                      Entities in this file
                    </h4>
                    <ul className="space-y-1">
                      {fileEntities.map((n) => (
                        <li
                          key={n.id}
                          className="font-mono text-xs border-2 border-base-300 px-2 py-1"
                        >
                          {n.label} <span className="text-base-content/40">({n.kind})</span>
                        </li>
                      ))}
                    </ul>
                  </section>
                )}
              </>
            ) : (
              <section className="space-y-2">
                <h4 className="font-mono text-[10px] uppercase tracking-widest text-base-content/40">
                  Code
                </h4>
                <pre className="bg-base-300 border-2 border-base-300 p-3 text-xs font-mono leading-relaxed max-h-72 overflow-y-auto overflow-x-auto">
                  <code>{selected.content || "(no code available)"}</code>
                </pre>
              </section>
            )}
          </div>
        </aside>
      )}
    </div>
  );
}
