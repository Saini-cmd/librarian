import { useMarkdown } from "../hooks/useMarkdown";

export default function MessageContent({ role, content }) {
  const html = useMarkdown(role === "assistant" ? content : "");

  if (role === "assistant") {
    return <div dangerouslySetInnerHTML={{ __html: html }} />;
  }
  return <div className="whitespace-pre-wrap">{content}</div>;
}
