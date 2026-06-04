
import { useMemo, useState, useEffect, useRef, useCallback } from "react";
import { marked } from "marked";
import DOMPurify from "dompurify";

const stages = [
  { key: "ingest", label: "Ingesting repo" },
  { key: "scan", label: "Scanning files" },
  { key: "chunk", label: "Chunking code" },
  { key: "embed", label: "Embedding chunks" },
  { key: "ready", label: "Ready for chat" },
];

// Helper to render markdown — works with marked v4 (sync) and v5+ (async)
const useMarkdown = (content) => {
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
    } catch (err) {
      console.error("Markdown parsing error:", err);
      if (mounted) setHtml(DOMPurify.sanitize(content || ""));
    }
    return () => { mounted = false; };
  }, [content]);
  return html;
};

// Helper to extract repo name from URL
const extractRepoName = (url) => {
  const parsed = url.replace(/\.git$/, "").split("/").pop();
  return parsed || "repo";
};

function App() {
  const [repoLink, setRepoLink] = useState("");
  const [mode, setMode] = useState("local");
  const [phase, setPhase] = useState("idle");
  const [statusText, setStatusText] = useState(
    "Paste a repository link to begin."
  );
  const [progress, setProgress] = useState(0);
  const [chatEnabled, setChatEnabled] = useState(false);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const pollRef = useRef(null);
  const abortControllerRef = useRef(null);

  const currentStage = useMemo(() => {
    if (phase === "processing") {
      if (progress < 20) return stages[0];
      if (progress < 40) return stages[1];
      if (progress < 70) return stages[2];
      if (progress < 100) return stages[3];
    }
    if (phase === "ready") return stages[4];
    return null;
  }, [phase, progress]);

  // Cleanup polling and streaming on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (abortControllerRef.current) abortControllerRef.current.abort();
    };
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

const startPollingStatus = useCallback(() => {
  if (pollRef.current) stopPolling();

  pollRef.current = setInterval(async () => {
    try {
      const res = await fetch("/api/status");
      if (!res.ok) throw new Error("Status fetch failed");
      const data = await res.json();

      // Debug logging - remove in production
      console.log("Status response:", data);

      // More robust status detection
      const isReady = 
        data.ready === true || 
        data.phase === "ready" || 
        data.status === "ready" ||
        data.state === "ready" ||
        (data.progress === 100 && data.complete === true);

      // Update progress based on what backend provides
      if (typeof data.progress === "number") {
        setProgress(data.progress);
      } else if (data.progress_percentage) {
        setProgress(data.progress_percentage);
      }

      // Update status text
      if (data.stage) setStatusText(data.stage);
      else if (data.message) setStatusText(data.message);
      else if (data.status) setStatusText(data.status);

      if (isReady) {
        console.log("Backend reports ready, stopping polling and enabling chat");
        stopPolling();
        setProgress(100);
        setPhase("ready");
        setChatEnabled(true);
        
        const statusMessage = data.message || 
                             data.status_message || 
                             "Repository ready — you can ask questions now.";
        setStatusText(statusMessage);

        // Force add welcome message if chat is empty or doesn't have assistant message
        setMessages((prev) => {
          // Check if any assistant message exists
          const hasAssistantMessage = prev.some((m) => m.role === "assistant");
          
          if (!hasAssistantMessage) {
            return [
              ...prev,
              {
                id: Date.now(),
                role: "assistant",
                content: "The repository is ready. Ask me anything about the codebase.",
              },
            ];
          }
          return prev;
        });
        
        // Important: Force re-render by triggering state update
        // This ensures the UI switches to chat view
        setMessages(prev => [...prev]); // This triggers a re-render
      }
    } catch (err) {
      console.error("Status polling error:", err);
      setStatusText((s) =>
        s.includes("failed") ? s : "Processing — awaiting backend updates..."
      );
      // Only advance progress if not already high
      setProgress((p) => Math.min(96, p + 2));
    }
  }, 2000); // Increased to 2 seconds to reduce load
}, [stopPolling]);

const startPipeline = async () => {
  if (phase === "processing") return;
  if (!repoLink.trim()) {
    setStatusText("Paste a repository link first.");
    return;
  }

  // Check if repo is already indexed
  try {
    const statusRes = await fetch("/api/status");
    const statusData = await statusRes.json();
    
    console.log("Status check before processing:", statusData);
    
    // More robust check for existing repo
    const isAlreadyReady = 
      statusData.ready === true || 
      statusData.phase === "ready" ||
      statusData.state === "ready";
      
    const repoName = extractRepoName(repoLink);
    const isCorrectRepo = statusData.indexed_repo_name === repoName ||
                          statusData.repo_name === repoName ||
                          statusData.repository === repoName;
    
    if (isAlreadyReady && isCorrectRepo) {
      console.log("Repo already indexed, skipping processing");
      setPhase("ready");
      setChatEnabled(true);
      setProgress(100);
      setStatusText("Repository already indexed — you can ask questions now.");
      
      setMessages((prev) => {
        const hasAssistantMessage = prev.some((m) => m.role === "assistant");
        if (!hasAssistantMessage) {
          return [
            ...prev,
            {
              id: Date.now(),
              role: "assistant",
              content: "The repository is already indexed and ready. Ask me anything about the codebase.",
            },
          ];
        }
        return prev;
      });
      return;
    }
  } catch (err) {
    console.log("Status check failed, proceeding with processing:", err);
  }

  // Reset chat before new processing
  setMessages([]); // Clear old messages
  setPhase("processing");
  setChatEnabled(false);
  setProgress(5);
  setStatusText("Starting pipeline — cloning repository...");

  try {
    const response = await fetch("/api/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        repo_url: repoLink.trim(),
        mode,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(errorText || "Pipeline request failed");
    }

    const data = await response.json();
    console.log("Process response:", data);
    setStatusText(data.message || "Repository processing started.");
    startPollingStatus();
  } catch (error) {
    console.error("Pipeline error:", error);
    setPhase("idle");
    setProgress(0);
    setStatusText(`Pipeline failed to start: ${error.message}`);
    setMessages((prev) => [
      ...prev,
      {
        id: Date.now(),
        role: "assistant",
        content: `Pipeline failed to start. Please check the backend and try again.\n\nError: ${error.message}`,
      },
    ]);
  }
};

  const submitMessage = async (event) => {
    event.preventDefault();
    if (!draft.trim() || !chatEnabled) return;

    const userMessage = draft.trim();
    setMessages((prev) => [
      ...prev,
      { id: Date.now(), role: "user", content: userMessage },
    ]);
    setDraft("");

    const placeholderId = Date.now() + 1;
    setMessages((prev) => [
      ...prev,
      { id: placeholderId, role: "assistant", content: "" },
    ]);

    // Abort previous streaming if any
    if (abortControllerRef.current) abortControllerRef.current.abort();
    abortControllerRef.current = new AbortController();

    try {
      const res = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userMessage, mode }),
        signal: abortControllerRef.current.signal,
      });

      if (!res.ok || !res.body) {
        const text = await res.text();
        throw new Error(text || "Streaming chat failed");
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let assembled = "";
      let doneStream = false;

      while (!doneStream) {
        const { value, done } = await reader.read();
        doneStream = done;
        if (value) {
          buffer += decoder.decode(value, { stream: true });
          // split by double newline (SSE standard)
          const parts = buffer.split("\n\n");
          buffer = parts.pop();

          for (const part of parts) {
            const lines = part.split("\n");
            for (const line of lines) {
              if (line.startsWith("data:")) {
                const payload = line.slice(5).trim();
                if (payload === "[DONE]") {
                  doneStream = true;
                  break;
                }
                try {
                  const event = JSON.parse(payload);
                  if (event.done) {
                    doneStream = true;
                    break;
                  }
                  if (typeof event.token === "string") {
                    assembled += event.token;
                    setMessages((prev) =>
                      prev.map((msg) =>
                        msg.id === placeholderId
                          ? { ...msg, content: assembled }
                          : msg
                      )
                    );
                  }
                } catch (e) {
                  console.warn("Failed to parse SSE event:", payload);
                }
              }
            }
          }
        }
      }
    } catch (err) {
      if (err.name === "AbortError") {
        console.log("Streaming aborted");
        return;
      }
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 2,
          role: "assistant",
          content: `Chat failed: ${err.message}`,
        },
      ]);
      // Remove the placeholder if it's still empty
      setMessages((prev) =>
        prev.filter((msg) => msg.id !== placeholderId || msg.content)
      );
    } finally {
      abortControllerRef.current = null;
    }
  };

  // Markdown-aware message component
  const MessageContent = ({ role, content }) => {
    const html = useMarkdown(role === "assistant" ? content : "");
    if (role === "assistant") {
      return <div dangerouslySetInnerHTML={{ __html: html }} />;
    }
    return <div>{content}</div>;
  };

  return (
    <div className="app-shell">
      <div className="bg-orb bg-orb-one" />
      <div className="bg-orb bg-orb-two" />

      <main className="layout">
        {phase === "ready" ? (
          <section
            className={`screen-panel chat-panel ${
              chatEnabled ? "chat-panel-ready" : "chat-panel-disabled"
            }`}
          >
            <div className="chat-header">
              <h2>Chat</h2>
              <span>{chatEnabled ? "Ready" : "Waiting for processing"}</span>
            </div>

            <div className="chat-stream">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`message message-${message.role}`}
                >
                  <MessageContent
                    role={message.role}
                    content={message.content}
                  />
                </div>
              ))}
            </div>

            <form className="chat-form" onSubmit={submitMessage}>
              <input
                disabled={!chatEnabled}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder={
                  chatEnabled
                    ? "Ask about the repository..."
                    : "Processing must complete first"
                }
              />
              <button type="submit" disabled={!chatEnabled}>
                Send
              </button>
            </form>
          </section>
        ) : (
          <section className="screen-panel hero-panel">
            <div className="brand-block">
              <h1>Librarian AI</h1>
              <p>
                Unleash the power of AI to navigate and understand your codebase
                like never before!
              </p>
            </div>

            <div className="input-row clean-input-row">
              <input
                id="repo-link"
                value={repoLink}
                onChange={(e) => setRepoLink(e.target.value)}
                placeholder="Paste GitHub repo URL"
              />
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value)}
                style={{ marginRight: 8 }}
              >
                <option value="local">Local (Ollama)</option>
                <option value="external">External (DeepSeek)</option>
              </select>



              <button
                type="button"
                onClick={startPipeline}
                disabled={phase === "processing"}
              >
                {phase === "processing" ? "Processing…" : "Process repository"}
              </button>
            </div>

            {phase === "processing" && (
              <div className="progress-row">
                <div className="progress-header">
                  <span className="status-text">{statusText}</span>
                </div>
                <div className="progress-track" aria-label="pipeline progress">
                  <div
                    className="progress-fill"
                    style={{ width: `${progress}%` }}
                  />
                </div>
                <div className="progress-footnote">
                  {Math.round(progress)}% complete
                </div>
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  );
}

export default App;