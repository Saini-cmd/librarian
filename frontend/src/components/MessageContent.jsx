import { useEffect, useState } from "react";
import { useMarkdown } from "../hooks/useMarkdown";

const CITATION_RE = /\[(C\d+)\]/g;

const CHIP_CLASS =
  "inline-flex items-center rounded-full bg-primary/10 text-primary font-mono text-[11px] font-semibold px-2 py-0.5 align-baseline mx-0.5 cursor-pointer transition-all hover:bg-primary/20 active:scale-95";

function linkCitations(html, citations) {
  if (!citations || citations.length === 0 || !html) return html;
  const ids = new Set(citations.map((c) => c.citation_id));
  const doc = new DOMParser().parseFromString(html, "text/html");
  const walker = document.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (node.parentElement?.closest("pre, code, a, button")) {
        return NodeFilter.FILTER_REJECT;
      }
      return NodeFilter.FILTER_ACCEPT;
    },
  });

  const textNodes = [];
  while (walker.nextNode()) textNodes.push(walker.currentNode);

  for (const node of textNodes) {
    const matches = [...node.nodeValue.matchAll(CITATION_RE)].filter((m) => ids.has(m[1]));
    if (matches.length === 0) continue;

    const frag = document.createDocumentFragment();
    let last = 0;
    for (const m of matches) {
      if (m.index > last) {
        frag.appendChild(document.createTextNode(node.nodeValue.slice(last, m.index)));
      }
      const btn = document.createElement("button");
      btn.type = "button";
      btn.dataset.citation = m[1];
      btn.textContent = m[0];
      btn.className = CHIP_CLASS;
      btn.setAttribute("aria-label", `View citation ${m[1]}`);
      frag.appendChild(btn);
      last = m.index + m[0].length;
    }
    if (last < node.nodeValue.length) {
      frag.appendChild(document.createTextNode(node.nodeValue.slice(last)));
    }
    node.parentNode.replaceChild(frag, node);
  }

  return doc.body.innerHTML;
}

export default function MessageContent({ role, content, citations, onCitationClick }) {
  const html = useMarkdown(role === "assistant" ? content : "");
  const [linked, setLinked] = useState("");

  useEffect(() => {
    setLinked(linkCitations(html, citations));
  }, [html, citations]);

  function handleClick(e) {
    const btn = e.target.closest?.("[data-citation]");
    if (!btn) return;
    e.preventDefault();
    const cid = btn.dataset.citation;
    const citation = citations?.find((c) => c.citation_id === cid);
    if (citation) onCitationClick?.(citation, btn.getBoundingClientRect());
  }

  if (role === "assistant") {
    return (
      <div
        className="prose prose-invert prose-sm max-w-none text-base-content"
        onClick={handleClick}
        dangerouslySetInnerHTML={{ __html: linked || html }}
      />
    );
  }
  return <div className="whitespace-pre-wrap">{content}</div>;
}
