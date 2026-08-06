import { useEffect, useMemo, useRef, useState } from "react";

import { getFileSummary } from "../api/client";
import MessageContent from "./MessageContent";
import SymbolGraph2DView from "./SymbolGraph2DView";

export default function SymbolGraphView({ graph, loading, error }) {
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

  async function handleNodeSelect(data) {
    const token = ++fetchToken.current;
    if (typeRef.current) clearInterval(typeRef.current);
    setSelected(data);
    setSummary("");
    setSummaryError("");
    setSummaryLoading(false);

    if (!data || data.kind !== "file") return;

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
        ) : !graph || graph.nodes.length === 0 ? (
          <div className="flex items-center justify-center h-full text-base-content/40 font-mono text-xs uppercase tracking-widest">
            No symbol data for this repo
          </div>
        ) : (
          <SymbolGraph2DView
            graph={graph}
            selectedId={selected?.id}
            onSelect={handleNodeSelect}
          />
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
                          {n.label}{" "}
                          <span className="text-base-content/40">({n.kind})</span>
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
