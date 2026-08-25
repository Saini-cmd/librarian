import { useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "@clerk/clerk-react";

import { getFileChunks } from "../api/client";
import { consumeSSE, readError } from "../api/sse";
import MessageContent from "./MessageContent";
import QuotaNotice from "./QuotaNotice";
import SymbolGraph2DView from "./SymbolGraph2DView";
import { IconChevronsLeft } from "../icons/Icon";

import { API_BASE_URL } from "../api/config";

function assembleFileCode(chunks) {
  if (!chunks || chunks.length === 0) return "";
  const sorted = [...chunks].sort(
    (a, b) => a.start_line - b.start_line || b.end_line - a.end_line
  );
  const parts = [];
  let covered = 0;
  for (const chunk of sorted) {
    if (chunk.end_line <= covered) continue;
    const overlap = Math.max(0, covered - chunk.start_line + 1);
    if (overlap > 0) {
      parts.push(chunk.content.split("\n").slice(overlap).join("\n"));
    } else {
      parts.push(chunk.content);
    }
    covered = chunk.end_line;
  }
  return parts.join("\n");
}

export default function SymbolGraphView({ graph, loading, error, repoHash }) {
  const { getToken } = useAuth();
  const [selected, setSelected] = useState(null);
  const [fileChunks, setFileChunks] = useState([]);
  const [fileChunksLoading, setFileChunksLoading] = useState(false);
  const [fileChunksError, setFileChunksError] = useState("");
  const [explainText, setExplainText] = useState("");
  const [explainLoading, setExplainLoading] = useState(false);
  const [explainError, setExplainError] = useState("");
  const [quota, setQuota] = useState(null);
  const [panelOpen, setPanelOpen] = useState(true);
  const explainTokenRef = useRef(0);
  const explainAbortRef = useRef(null);

  useEffect(() => {
    setSelected(null);
    setFileChunks([]);
    setFileChunksLoading(false);
    setFileChunksError("");
    setExplainText("");
    setExplainLoading(false);
    setExplainError("");
  }, [graph?.repo, repoHash]);

  const fileCode = useMemo(() => assembleFileCode(fileChunks), [fileChunks]);

  useEffect(() => {
    if (!selected || selected.kind !== "file") return undefined;
    let cancelled = false;
    setFileChunks([]);
    setFileChunksLoading(true);
    setFileChunksError("");
    if (!repoHash) {
      setFileChunksLoading(false);
      setFileChunksError("No commit hash for this repo");
      return undefined;
    }
    getFileChunks(repoHash, selected.file)
      .then((data) => {
        if (!cancelled) setFileChunks(data || []);
      })
      .catch((err) => {
        if (!cancelled) setFileChunksError(err.message || "Failed to load file code");
      })
      .finally(() => {
        if (!cancelled) setFileChunksLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selected, repoHash]);

  function handleNodeSelect(data) {
    setSelected(data);
    setPanelOpen(true);
    setFileChunks([]);
    setExplainText("");
    setExplainLoading(false);
    setExplainError("");
  }

  const fileEntities = useMemo(() => {
    if (!graph || !selected || selected.kind !== "file") return [];
    return graph.nodes.filter((n) => n.kind !== "file" && n.file === selected.file);
  }, [graph, selected]);

  const codeToExplain = selected && (selected.kind === "file" ? fileCode : selected.content);

  async function handleExplain() {
    if (!selected || !codeToExplain || explainLoading || !repoHash) return;
    const token = ++explainTokenRef.current;
    explainAbortRef.current?.abort();
    const controller = new AbortController();
    explainAbortRef.current = controller;
    setExplainLoading(true);
    setExplainError("");
    setExplainText("");
    setQuota(null);
    try {
      const headers = { "Content-Type": "application/json" };
      const t = await getToken();
      if (t) headers.Authorization = `Bearer ${t}`;

      const res = await fetch(
  `${API_BASE_URL}/repositories/${encodeURIComponent(repoHash)}/explain`,
  {
        method: "POST",
        headers,
        body: JSON.stringify({
          file_path: selected.file,
          kind: selected.kind,
          label: selected.label,
          start_line: selected.start_line,
          end_line: selected.end_line,
          code: codeToExplain,
        }),
        signal: controller.signal,
      });

      if (!res.ok || !res.body) {
        const { message, quota: q } = await readError(res);
        if (q) {
          setQuota(q);
          return;
        }
        throw new Error(message);
      }

      await consumeSSE(res, (ev) => {
        if (token !== explainTokenRef.current) return;
        if (ev.token) setExplainText((prev) => prev + ev.token);
        else if (ev.error) setExplainError(ev.error);
      });
    } catch (err) {
      if (token === explainTokenRef.current) {
        setExplainError(
          err.name === "AbortError" ? "Explanation stopped" : err.message || "Explain failed"
        );
      }
    } finally {
      if (token === explainTokenRef.current) {
        setExplainLoading(false);
        if (explainAbortRef.current === controller) explainAbortRef.current = null;
      }
    }
  }

  function stopExplain() {
    explainAbortRef.current?.abort();
  }

  return (
    <div className="flex-1 min-h-0 flex relative">
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

      {selected && panelOpen && (
        <aside className="absolute inset-0 z-40 w-full glass-surface flex flex-col min-h-0 border-t lg:border-t-0 lg:border-l border-base-content/10 lg:static lg:z-auto lg:w-96 shrink-0">
          <div className="p-4 border-b border-base-content/10 flex items-start justify-between gap-2">
            <div className="min-w-0 flex items-center gap-2">
              <button
                className="btn btn-circle btn-ghost btn-sm shrink-0"
                onClick={() => setPanelOpen(false)}
                title="Close details"
                aria-label="Close details"
              >
                <IconChevronsLeft className="w-4 h-4" />
              </button>
              <div className="min-w-0 space-y-1">
                <div className="font-mono text-[0.625rem] uppercase tracking-widest text-primary">
                  {selected.kind}
                </div>
                <h3 className="font-semibold text-sm text-base-content truncate">{selected.label}</h3>
              </div>
            </div>
            <button
              className="btn btn-sm btn-primary shrink-0"
              onClick={handleExplain}
              disabled={!codeToExplain || explainLoading}
              title={codeToExplain ? "Explain this code" : "Code not available yet"}
            >
              {explainLoading ? (
                <>
                  <span className="loading loading-spinner loading-xs" />
                  Explaining
                </>
              ) : (
                "Explain"
              )}
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            <div className="font-mono text-[0.625rem] text-base-content/50 truncate" title={selected.file}>
              {selected.file}
              {selected.start_line ? `:${selected.start_line}-${selected.end_line}` : ""}
            </div>

            {selected.kind === "file" ? (
              <>
                {fileEntities.length > 0 && (
                  <section className="space-y-2">
                    <h4 className="font-mono text-[0.625rem] uppercase tracking-widest text-base-content/40">
                      Entities in this file
                    </h4>
                    <ul className="flex flex-wrap gap-1.5">
                      {fileEntities.map((n) => (
                        <li
                          key={n.id}
                          className="font-mono text-xs rounded-lg bg-base-content/5 px-2 py-1"
                        >
                          {n.label}{" "}
                          <span className="text-base-content/40">({n.kind})</span>
                        </li>
                      ))}
                    </ul>
                  </section>
                )}

                <section className="space-y-2">
                  <h4 className="font-mono text-[0.625rem] uppercase tracking-widest text-base-content/40">
                    Complete code
                  </h4>
                  {fileChunksLoading ? (
                    <span className="loading loading-dots loading-sm" />
                  ) : fileChunksError ? (
                    <p className="text-xs font-mono text-base-content/50">{fileChunksError}</p>
                  ) : (
                    <pre className="bg-base-content/5 rounded-xl border border-base-content/10 p-3 text-xs font-mono leading-relaxed max-h-96 overflow-y-auto overflow-x-auto">
                      <code>{fileCode || "(no code available)"}</code>
                    </pre>
                  )}
                </section>
              </>
            ) : (
              <section className="space-y-2">
                <h4 className="font-mono text-[0.625rem] uppercase tracking-widest text-base-content/40">
                  Code
                </h4>
                <pre className="bg-base-content/5 rounded-xl border border-base-content/10 p-3 text-xs font-mono leading-relaxed max-h-72 overflow-y-auto overflow-x-auto">
                  <code>{selected.content || "(no code available)"}</code>
                </pre>
              </section>
            )}

            {(explainLoading || explainText || explainError || quota) && (
              <section className="space-y-2 border-t border-base-content/10 pt-3">
                <div className="flex items-center justify-between">
                  <h4 className="font-mono text-[0.625rem] uppercase tracking-widest text-base-content/40">
                    Explanation
                  </h4>
                  {explainLoading && (
                    <button
                      className="btn btn-xs btn-ghost font-mono"
                      onClick={stopExplain}
                    >
                      Stop
                    </button>
                  )}
                </div>
                {explainLoading && !explainText && (
                  <span className="loading loading-dots loading-sm" />
                )}
                {quota && (
                  <QuotaNotice quota={quota} onDismiss={() => setQuota(null)} />
                )}
                {explainError && (
                  <p className="text-xs font-mono text-error">{explainError}</p>
                )}
                {explainText && (
                  <div className="text-sm leading-relaxed">
                    <MessageContent role="assistant" content={explainText} />
                  </div>
                )}
              </section>
            )}
          </div>
        </aside>
      )}
    </div>
  );
}
