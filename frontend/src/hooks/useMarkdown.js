import { useState, useEffect } from "react";
import { marked } from "marked";
import DOMPurify from "dompurify";

export function useMarkdown(content) {
  const [html, setHtml] = useState("");
  useEffect(() => {
    let mounted = true;
    try {
      const result = marked.parse(content || "", { mangle: false, headerIds: false });
      if (result && typeof result.then === "function") {
        result
          .then((parsed) => { if (mounted) setHtml(DOMPurify.sanitize(parsed)); })
          .catch(() => { if (mounted) setHtml(DOMPurify.sanitize(content || "")); });
      } else {
        if (mounted) setHtml(DOMPurify.sanitize(result));
      }
    } catch {
      if (mounted) setHtml(DOMPurify.sanitize(content || ""));
    }
    return () => { mounted = false; };
  }, [content]);
  return html;
}
