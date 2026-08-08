import { useState, useEffect, useRef, useCallback } from "react";
import { useAuth } from "@clerk/clerk-react";
import Layout from "../components/Layout";
import RepoInput from "../components/RepoInput";
import ProgressBar from "../components/ProgressBar";
import ChatMessages from "../components/ChatMessages";
import CitationCard from "../components/CitationCard";
import SymbolGraphView from "../components/SymbolGraphView";
import {
  getStatus,
  getConversations,
  getConversation,
  deleteConversation,
  createConversation,
  getRepositories,
  getRepoGraph,
} from "../api/client";

const extractRepoName = (url) =>
  (url.replace(/\.git$/, "").split("/").pop()) || "repo";

export default function AppPage() {
  const { getToken, isSignedIn } = useAuth();
  const [phase, setPhase] = useState("idle");
  const [progress, setProgress] = useState(0);
  const [statusText, setStatusText] = useState("");
  const [chatEnabled, setChatEnabled] = useState(false);
  const [messages, setMessages] = useState([]);
  const [streaming, setStreaming] = useState(false);
  const [draft, setDraft] = useState("");
  const [conversations, setConversations] = useState([]);
  const [activeConvId, setActiveConvId] = useState(null);
  const [convLoading, setConvLoading] = useState(true);
  const [repositories, setRepositories] = useState([]);
  const [selectedRepo, setSelectedRepo] = useState(null);
  const [view, setView] = useState("chat");
  const [graph, setGraph] = useState(null);
  const [graphRepo, setGraphRepo] = useState(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphError, setGraphError] = useState("");
  const [openCitation, setOpenCitation] = useState(null);
  const abortRef = useRef(null);
  const pollRef = useRef(null);
  const msgIdRef = useRef(0);

  useEffect(() => {
    loadConversations();
    loadRepositories();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (abortRef.current) abortRef.current.abort();
    };
  }, []);

  useEffect(() => {
    if (view !== "graph" || !selectedRepo || graphRepo === selectedRepo) return;
    let cancelled = false;
    setGraphLoading(true);
    setGraphError("");
    getRepoGraph(selectedRepo)
      .then((data) => {
        if (cancelled) return;
        setGraph(data);
        setGraphRepo(selectedRepo);
      })
      .catch((err) => {
        if (!cancelled) setGraphError(err.message || "Failed to load graph");
      })
      .finally(() => {
        if (!cancelled) setGraphLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [view, selectedRepo, graphRepo]);

  async function loadRepositories() {
    try {
      const data = await getRepositories();
      setRepositories(Array.isArray(data) ? data : data?.repositories || []);
    } catch {
      setRepositories([]);
    }
  }

  async function loadConversations() {
    setConvLoading(true);
    try {
      const data = await getConversations();
      setConversations(Array.isArray(data) ? data : data?.conversations || []);
    } catch {
      setConversations([]);
    } finally {
      setConvLoading(false);
    }
  }

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startPolling = useCallback(() => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const data = await getStatus();
        if (typeof data.progress === "number") setProgress(data.progress);
        setStatusText(data.stage || data.message || "");
        if (data.ready || data.phase === "ready") {
          stopPolling();
          setPhase("ready");
          setProgress(100);
          setChatEnabled(true);
          setStatusText("Repository ready — ask questions now.");
          setSelectedRepo((prev) => prev || data.indexed_repo_name || null);
          await loadRepositories();
          await loadConversations();
        }
      } catch {
        setProgress((p) => Math.min(96, p + 2));
      }
    }, 2000);
  }, [stopPolling]);

  async function handleProcess(repoUrl) {
    const repoName = extractRepoName(repoUrl);
    const existing = repositories.find((r) => r.repo_name === repoName);
    if (existing) {
      setMessages([]);
      setPhase("ready");
      setChatEnabled(true);
      setSelectedRepo(existing.repo_name);
      setStatusText("Repo already indexed — opened a new chat.");
      try {
        const conv = await createConversation(undefined, existing.repo_name, existing.repo_url);
        setActiveConvId(conv?.id || null);
      } catch {
        setActiveConvId(null);
      }
      await loadConversations();
      return;
    }

    setMessages([]);
    setPhase("processing");
    setChatEnabled(false);
    setProgress(5);
    setStatusText("Cloning repository...");

    try {
      const headers = { "Content-Type": "application/json" };
      if (isSignedIn) {
        headers["Authorization"] = `Bearer ${await getToken()}`;
      }

      const res = await fetch("/api/process", {
        method: "POST",
        headers,
        body: JSON.stringify({ repo_url: repoUrl }),
      });

      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || "Pipeline request failed");
      }

      const data = await res.json();
      if (data?.conversation_id) setActiveConvId(data.conversation_id);

      setStatusText("Repository processing started.");
      startPolling();
    } catch (err) {
      setPhase("idle");
      setProgress(0);
      setStatusText(`Pipeline failed: ${err.message}`);
    }
  }

  async function handleSelectConversation(convId) {
    setActiveConvId(convId);
    setOpenCitation(null);
    try {
      const data = await getConversation(convId);
      setSelectedRepo(data.repo_name || null);
      setMessages(
        (data.messages || []).map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          citations: m.citations || [],
        }))
      );
      setPhase("ready");
      setChatEnabled(true);
    } catch {
      setMessages([]);
    }
  }

  async function handleNewChat() {
    setActiveConvId(null);
    setMessages([]);
    setOpenCitation(null);
    setSelectedRepo(null);
    setPhase("idle");
    setProgress(0);
    setChatEnabled(false);
    setStatusText("");
  }

  async function handleDeleteConversation(convId) {
    try {
      await deleteConversation(convId);
      if (activeConvId === convId) handleNewChat();
      await loadConversations();
    } catch {}
  }

  function handleCitationClick(citation, rect) {
    setOpenCitation((cur) =>
      cur && cur.citation.chunk_id === citation.chunk_id
        ? null
        : { citation, anchorRect: rect }
    );
  }

  async function submitMessage(e) {
    e.preventDefault();
    if (!draft.trim() || !chatEnabled) return;

    const userMsg = draft.trim();
    setDraft("");
    setOpenCitation(null);
    const userMsgId = `local-${++msgIdRef.current}`;
    const placeholderId = `local-${++msgIdRef.current}`;
    setMessages((prev) => [
      ...prev,
      { id: userMsgId, role: "user", content: userMsg },
      { id: placeholderId, role: "assistant", content: "" },
    ]);
    setStreaming(true);

    if (abortRef.current) abortRef.current.abort();
    abortRef.current = new AbortController();

    try {
      const headers = { "Content-Type": "application/json" };
      if (isSignedIn) {
        headers["Authorization"] = `Bearer ${await getToken()}`;
      }

      const res = await fetch("/api/chat/stream", {
        method: "POST",
        headers,
        body: JSON.stringify({
          message: userMsg,
          conversation_id: activeConvId,
          repo_name: selectedRepo,
        }),
        signal: abortRef.current.signal,
      });

      if (!res.ok || !res.body) {
        throw new Error("Streaming chat failed");
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let assembled = "";
      let finalCitations = [];
      let done = false;

      while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;
        if (value) {
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n\n");
          buffer = parts.pop();
          for (const part of parts) {
            for (const line of part.split("\n")) {
              if (line.startsWith("data:")) {
                const payload = line.slice(5).trim();
                if (payload === "[DONE]") { done = true; break; }
                try {
                  const event = JSON.parse(payload);
                  if (event.done) { done = true; break; }
                  if (event.citations) finalCitations = event.citations;
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
                } catch {}
              }
            }
          }
        }
      }

      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === placeholderId ? { ...msg, citations: finalCitations } : msg
        )
      );
      setStreaming(false);
    } catch (err) {
      if (err.name === "AbortError") return;
      setStreaming(false);
      setMessages((prev) =>
        prev.filter((msg) => msg.id !== placeholderId || msg.content)
      );
    }
  }

  return (
    <Layout
      conversations={conversations}
      activeConvId={activeConvId}
      onSelectConversation={handleSelectConversation}
      onNewChat={handleNewChat}
      onDeleteConversation={handleDeleteConversation}
      conversationsLoading={convLoading}
    >
      <div className="flex flex-col h-dvh overflow-hidden">
        {phase === "ready" ? (
          <>
            <div className="glass-nav px-6 py-3 flex items-center justify-between gap-4 shrink-0">
              <h1
                className="text-base font-semibold truncate text-base-content"
                title={selectedRepo || ""}
              >
                {selectedRepo ? selectedRepo : "No repo"}
              </h1>
              <div className="flex items-center rounded-full bg-base-content/5 p-1 shrink-0">
                <button
                  type="button"
                  className={`px-4 py-1.5 rounded-full text-xs font-medium transition-colors ${
                    view === "chat"
                      ? "bg-base-100 shadow-sm text-base-content"
                      : "text-base-content/50"
                  }`}
                  onClick={() => setView("chat")}
                  disabled={!chatEnabled || !selectedRepo}
                >
                  Chat
                </button>
                <button
                  type="button"
                  className={`px-4 py-1.5 rounded-full text-xs font-medium transition-colors ${
                    view === "graph"
                      ? "bg-base-100 shadow-sm text-base-content"
                      : "text-base-content/50"
                  }`}
                  onClick={() => {
                    setView("graph");
                    setOpenCitation(null);
                  }}
                  disabled={!chatEnabled || !selectedRepo}
                >
                  Graph
                </button>
              </div>
            </div>

            {view === "graph" ? (
              <SymbolGraphView
                graph={graph}
                loading={graphLoading}
                error={graphError}
              />
            ) : (
              <>
                <ChatMessages
                  messages={messages}
                  streaming={streaming}
                  onCitationClick={handleCitationClick}
                />

                {openCitation && (
                  <CitationCard
                    citation={openCitation.citation}
                    anchorRect={openCitation.anchorRect}
                    onClose={() => setOpenCitation(null)}
                  />
                )}

                <form
                  onSubmit={submitMessage}
                  className="px-4 pb-4 shrink-0"
                >
                  <div className="glass-composer rounded-full max-w-3xl mx-auto flex items-center gap-2 pl-5 pr-2 py-2">
                    <input
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      placeholder={
                        chatEnabled
                          ? "Ask about the repository..."
                          : "Processing must complete first"
                      }
                      className="flex-1 bg-transparent outline-none text-sm text-base-content placeholder:text-base-content/40"
                      disabled={!chatEnabled}
                    />
                    <button
                      type="submit"
                      className="btn btn-primary btn-circle btn-sm rounded-full shrink-0"
                      disabled={!chatEnabled || !draft.trim()}
                    >
                      <span className="text-base leading-none">➤</span>
                    </button>
                  </div>
                </form>
              </>
            )}
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center p-8 bg-base-100">
            <div className="w-full max-w-2xl mx-auto space-y-10">
              <div className="text-center space-y-2">
                <h2 className="text-4xl lg:text-5xl font-bold tracking-tight text-base-content">
                  Librarian AI
                </h2>
                <p className="text-base-content/50 text-sm">
                  Repository ingestion
                </p>
              </div>

              {phase === "processing" ? (
                <ProgressBar progress={progress} statusText={statusText} />
              ) : (
                <RepoInput onProcess={handleProcess} disabled={phase === "processing"} />
              )}
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
}
