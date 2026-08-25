import { useState, useEffect, useRef } from "react";
import { useAuth } from "@clerk/clerk-react";
import Layout from "../components/Layout";
import RepoInput from "../components/RepoInput";
import ProgressBar from "../components/ProgressBar";
import ChatMessages from "../components/ChatMessages";
import CitationCard from "../components/CitationCard";
import SymbolGraphView from "../components/SymbolGraphView";
import QuotaNotice from "../components/QuotaNotice";
import {
  getConversations,
  getConversation,
  deleteConversation,
  createConversation,
  getRepositories,
  getRepoGraph,
  getRepoUpdates,
} from "../api/client";
import { consumeSSE, readError } from "../api/sse";
import {
  IconSend,
  IconSync,
  IconChat,
  IconGraph,
} from "../icons/Icon";
import { API_BASE_URL } from "../api/config";

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
  const [selectedRepoHash, setSelectedRepoHash] = useState(null);
  const [updatesAvailable, setUpdatesAvailable] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncProgress, setSyncProgress] = useState(0);
  const [view, setView] = useState("chat");
  const [graph, setGraph] = useState(null);
  const [graphRepo, setGraphRepo] = useState(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphError, setGraphError] = useState("");
  const [openCitation, setOpenCitation] = useState(null);
  const [quota, setQuota] = useState(null);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const abortRef = useRef(null);
  const msgIdRef = useRef(0);

  useEffect(() => {
    loadConversations();
    loadRepositories();
    return () => {
      if (abortRef.current) abortRef.current.abort();
    };
  }, []);

  useEffect(() => {
    if (view !== "graph" || !selectedRepoHash || graphRepo === selectedRepoHash) return;
    let cancelled = false;
    setGraphLoading(true);
    setGraphError("");
    getRepoGraph(selectedRepoHash)
      .then((data) => {
        if (cancelled) return;
        setGraph(data);
        setGraphRepo(selectedRepoHash);
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
  }, [view, selectedRepoHash, graphRepo]);

  useEffect(() => {
    if (!selectedRepoHash) {
      setUpdatesAvailable(false);
      return;
    }
    let cancelled = false;
    getRepoUpdates(selectedRepoHash)
      .then((data) => {
        if (!cancelled) setUpdatesAvailable(!!data?.updates_available);
      })
      .catch(() => {
        if (!cancelled) setUpdatesAvailable(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedRepoHash]);

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

  async function handleProcess(repoUrl) {
    setQuota(null);
    const repoName = extractRepoName(repoUrl);
    const existing = repositories.find((r) => r.repo_name === repoName);
    if (existing) {
      setMessages([]);
      setPhase("ready");
      setChatEnabled(true);
      setSelectedRepo(existing.repo_name);
      setSelectedRepoHash(existing.repo_hash);
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

      const res = await fetch(`${API_BASE_URL}/process`, {
        method: "POST",
        headers,
        body: JSON.stringify({ repo_url: repoUrl }),
      });

      if (!res.ok || !res.body) {
        const { message, quota: q } = await readError(res);
        if (q) {
          setQuota(q);
          setPhase("idle");
          setProgress(0);
          setStatusText("");
          return;
        }
        throw new Error(message);
      }

      let result = null;
      await consumeSSE(res, (event) => {
        if (event.type === "progress") {
          setProgress(event.progress);
          setStatusText(event.message);
        } else if (event.type === "result") {
          result = event.result;
        } else if (event.type === "error") {
          throw new Error(event.error);
        }
      });

      if (result) {
        if (result.conversation_id) setActiveConvId(result.conversation_id);
        setSelectedRepo(result.repo_name || null);
        setSelectedRepoHash(result.repo_hash || null);
        setPhase("ready");
        setChatEnabled(true);
        setProgress(100);
        setStatusText(result.message || "Repository ready — ask questions now.");
        await loadRepositories();
        await loadConversations();
      }
    } catch (err) {
      setPhase("idle");
      setProgress(0);
      setStatusText(`Pipeline failed: ${err.message}`);
    }
  }

  async function handleSelectConversation(convId) {
    setActiveConvId(convId);
    setOpenCitation(null);
    setMessagesLoading(true);
    try {
      const data = await getConversation(convId);
      setSelectedRepo(data.repo_name || null);
      setSelectedRepoHash(data.repo_hash || null);
      setMessages(
        (data.messages || []).map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          citations: m.citations || [],
          repo_hash: m.repo_hash || null,
        }))
      );
      setPhase("ready");
      setChatEnabled(true);
    } catch {
      setMessages([]);
    } finally {
      setMessagesLoading(false);
    }
  }

  async function handleNewChat() {
    setActiveConvId(null);
    setMessages([]);
    setMessagesLoading(false);
    setOpenCitation(null);
    setQuota(null);
    setSelectedRepo(null);
    setSelectedRepoHash(null);
    setUpdatesAvailable(false);
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

  async function handleSync() {
    if (!selectedRepoHash || syncing) return;
    setQuota(null);
    setSyncing(true);
    try {
      const headers = { "Content-Type": "application/json" };
      if (isSignedIn) headers["Authorization"] = `Bearer ${await getToken()}`;
      const res = await fetch(
  `${API_BASE_URL}/repositories/${encodeURIComponent(selectedRepoHash)}/sync`,
        { method: "POST", headers }
      );
      if (!res.ok || !res.body) {
        const { message, quota: q } = await readError(res);
        if (q) {
          setQuota(q);
          return;
        }
        throw new Error(message);
      }

      let result = null;
      await consumeSSE(res, (event) => {
        if (event.type === "progress") {
          setSyncProgress(event.progress);
          setStatusText(event.message);
        } else if (event.type === "result") {
          result = event.result;
        } else if (event.type === "error") {
          throw new Error(event.error);
        }
      });

      if (result?.status === "up_to_date") {
        setUpdatesAvailable(false);
        setStatusText("Repository is already up to date.");
      } else if (result?.status === "synced") {
        setUpdatesAvailable(false);
        setStatusText(
          `Synced to latest commit (${String(result.repo_hash || "").slice(0, 7)}).`
        );
        await loadRepositories();
        await loadConversations();
        if (activeConvId) await handleSelectConversation(activeConvId);
      } else {
        setStatusText("Sync completed.");
      }
    } catch (err) {
      setStatusText(`Sync failed: ${err.message}`);
    } finally {
      setSyncing(false);
      setSyncProgress(0);
    }
  }

  async function submitMessage(e) {
    e.preventDefault();
    if (!draft.trim() || !chatEnabled) return;

    const userMsg = draft.trim();
    setDraft("");
    setOpenCitation(null);
    setQuota(null);
    const userMsgId = `local-${++msgIdRef.current}`;
    const placeholderId = `local-${++msgIdRef.current}`;
    setMessages((prev) => [
      ...prev,
      { id: userMsgId, role: "user", content: userMsg, repo_hash: selectedRepoHash },
      { id: placeholderId, role: "assistant", content: "", repo_hash: selectedRepoHash },
    ]);
    setStreaming(true);

    if (abortRef.current) abortRef.current.abort();
    abortRef.current = new AbortController();

    try {
      const headers = { "Content-Type": "application/json" };
      if (isSignedIn) {
        headers["Authorization"] = `Bearer ${await getToken()}`;
      }

      const res = await fetch(`${API_BASE_URL}/chat/stream`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          message: userMsg,
          conversation_id: activeConvId,
          repo_hash: selectedRepoHash,
        }),
        signal: abortRef.current.signal,
      });

      if (!res.ok || !res.body) {
        const { message, quota: q } = await readError(res);
        if (q) {
          setQuota(q);
          setStreaming(false);
          setMessages((prev) =>
            prev.filter(
              (msg) => msg.id !== userMsgId && msg.id !== placeholderId
            )
          );
          setDraft(userMsg);
          return;
        }
        throw new Error(message);
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
      if (err.message) {
        setMessages((prev) => [
          ...prev,
          {
            id: `local-${++msgIdRef.current}`,
            role: "assistant",
            content: err.message,
            repo_hash: selectedRepoHash,
          },
        ]);
      }
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
            <div className="glass-nav py-3 pr-6 pl-14 lg:pl-6 flex items-center justify-between gap-4 shrink-0">
              <h1
                className="text-base font-semibold truncate text-base-content"
                title={selectedRepo || ""}
              >
                {selectedRepo ? selectedRepo : "No repo"}
              </h1>
              <div className="flex items-center gap-2 shrink-0">
                {updatesAvailable && !syncing && (
                  <span className="hidden md:inline text-xs font-medium text-warning">
                    Update available
                  </span>
                )}
                <button
                  type="button"
                  className="btn btn-sm btn-neutral rounded-full"
                  onClick={handleSync}
                  disabled={syncing || !selectedRepoHash}
                >
                  <IconSync className="w-4 h-4" />
                  {syncing ? "Syncing…" : "Sync"}
                </button>
                <div className="flex items-center rounded-full bg-base-content/5 p-1 shrink-0">
                <button
                  type="button"
                  className={`px-2.5 lg:px-4 py-1.5 rounded-full text-xs font-medium transition-colors inline-flex items-center gap-1.5 ${
                    view === "chat"
                      ? "bg-primary text-primary-content shadow-sm"
                      : "text-base-content/50"
                  }`}
                  onClick={() => setView("chat")}
                  disabled={!chatEnabled || !selectedRepo}
                >
                  <IconChat className="w-3.5 h-3.5" />
                  <span className="hidden lg:inline">Chat</span>
                </button>
                <button
                  type="button"
                  className={`px-2.5 lg:px-4 py-1.5 rounded-full text-xs font-medium transition-colors inline-flex items-center gap-1.5 ${
                    view === "graph"
                      ? "bg-primary text-primary-content shadow-sm"
                      : "text-base-content/50"
                  }`}
                  onClick={() => {
                    setView("graph");
                    setOpenCitation(null);
                  }}
                  disabled={!chatEnabled || !selectedRepo}
                >
                  <IconGraph className="w-3.5 h-3.5" />
                  <span className="hidden lg:inline">Graph</span>
                </button>
              </div>
              </div>
            </div>

            {quota && (
              <div className="px-6 pt-3">
                <QuotaNotice quota={quota} onDismiss={() => setQuota(null)} />
              </div>
            )}

            {view === "graph" ? (
              <SymbolGraphView
                graph={graph}
                loading={graphLoading}
                error={graphError}
                repoHash={graphRepo}
              />
            ) : (
              <>
                <ChatMessages
                  key={activeConvId}
                  messages={messages}
                  streaming={streaming}
                  onCitationClick={handleCitationClick}
                  repoHash={selectedRepoHash}
                  loading={messagesLoading}
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
                      <IconSend className="w-4 h-4" />
                    </button>
                  </div>
                </form>
              </>
            )}
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center p-8 bg-base-100">
            <div className="w-full max-w-2xl mx-auto space-y-10">
              {quota && (
                <QuotaNotice quota={quota} onDismiss={() => setQuota(null)} />
              )}
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
        {syncing && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-base-100/90 p-6">
            <div className="w-full max-w-2xl space-y-3">
              <div
                className="text-center font-mono text-[0.6875rem] uppercase tracking-widest text-base-content/60 truncate"
                title={selectedRepo || ""}
              >
                Syncing {selectedRepo || "repository"}
              </div>
              <ProgressBar progress={syncProgress} statusText={statusText} />
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
}
