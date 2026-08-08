import { useCallback, useEffect, useRef, useState } from "react";
import { getChunk } from "../api/client";

const CARD_WIDTH = 340;
const GAP = 10;

export default function CitationCard({ citation, anchorRect, onClose }) {
  const [chunk, setChunk] = useState(null);
  const [error, setError] = useState("");
  const [pos, setPos] = useState({ top: 0, left: 0, width: CARD_WIDTH, placeAbove: false });
  const cardRef = useRef(null);
  const preRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    setChunk(null);
    setError("");
    const repo = citation.repo || citation.repo_name;
    if (!repo || !citation.chunk_id) {
      setError("Missing chunk reference");
      return undefined;
    }
    getChunk(repo, citation.chunk_id)
      .then((data) => {
        if (!cancelled) setChunk(data);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message || "Failed to load chunk");
      });
    return () => {
      cancelled = true;
    };
  }, [citation.chunk_id, citation.repo, citation.repo_name]);

  const place = useCallback(() => {
    const el = cardRef.current;
    if (!el) return;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const height = el.offsetHeight;
    const width = Math.min(CARD_WIDTH, vw - 16);
    const left = Math.max(8, Math.min(anchorRect.left, vw - width - 8));
    const placeAbove = anchorRect.bottom + GAP + height > vh;
    const top = placeAbove
      ? Math.max(8, anchorRect.top - GAP - height)
      : anchorRect.bottom + GAP;
    setPos({ top, left, width, placeAbove });
  }, [anchorRect]);

  useEffect(() => {
    place();
  }, [place, chunk, error]);

  useEffect(() => {
    const el = cardRef.current;
    if (!el) return;
    function onWheel(e) {
      e.preventDefault();
      const pre = preRef.current;
      if (pre) pre.scrollTop += e.deltaY;
    }
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  useEffect(() => {
    function onDocClick(e) {
      if (!cardRef.current?.contains(e.target)) onClose();
    }
    function onKey(e) {
      if (e.key === "Escape") onClose();
    }
    function onScroll(e) {
      if (cardRef.current?.contains(e.target)) return;
      onClose();
    }
    function onResize() {
      onClose();
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    document.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onResize);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onResize);
    };
  }, [onClose]);

  return (
    <div
      ref={cardRef}
      role="dialog"
      aria-label={`Citation ${citation.citation_id}`}
      style={{
        position: "fixed",
        top: pos.top,
        left: pos.left,
        width: pos.width,
        zIndex: 50,
      }}
      className="clay rounded-3xl bg-base-100 p-4 shadow-xl"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-mono text-[10px] uppercase tracking-widest text-primary">
            Citation · {citation.citation_id}
          </div>
          <div
            className="mt-1 font-mono text-[11px] text-base-content/60 truncate"
            title={citation.file_path}
          >
            {citation.file_path}:{citation.start_line}-{citation.end_line}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close citation"
          className="btn btn-circle btn-ghost btn-xs shrink-0"
        >
          ✕
        </button>
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5">
        {citation.symbol && (
          <span className="font-mono text-[10px] rounded-full bg-primary/10 text-primary px-2 py-0.5">
            {citation.symbol}
          </span>
        )}
        {chunk?.language && (
          <span className="font-mono text-[10px] rounded-full bg-base-content/5 text-base-content/60 px-2 py-0.5">
            {chunk.language}
          </span>
        )}
      </div>

      <div className="mt-3">
        {!chunk && !error ? (
          <div className="flex items-center gap-2 text-xs text-base-content/50 py-2">
            <span className="loading loading-dots loading-sm" />
            Loading chunk...
          </div>
        ) : error ? (
          <p className="text-xs font-mono text-base-content/50">{error}</p>
        ) : (
          <pre
            ref={preRef}
            className="bg-base-content/5 rounded-xl border border-base-content/10 p-3 text-xs font-mono leading-relaxed max-h-64 overflow-auto"
          >
            <code>{chunk.content}</code>
          </pre>
        )}
      </div>
    </div>
  );
}
