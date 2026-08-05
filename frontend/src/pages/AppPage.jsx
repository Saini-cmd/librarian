import { useState, useEffect, useRef, useCallback } from "react";
import { useAuth } from "@clerk/clerk-react";
import Layout from "../components/Layout";
import RepoInput from "../components/RepoInput";
import ProgressBar from "../components/ProgressBar";
import ChatMessages from "../components/ChatMessages";
import {
  getStatus,
  processRepo,
  getConversations,
  deleteConversation,
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
  const abortRef = useRef(null);
  const pollRef = useRef(null);

  useEffect(() => {
    loadConversations();
    checkExistingStatus();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (abortRef.current) abortRef.current.abort();
    };
  }, []);

  async function checkExistingStatus() {
    try {
      const status = await getStatus();
      if (status.ready || status.phase === "ready") {
        setPhase("ready");
        setProgress(100);
        setChatEnabled(true);
        setStatusText("Repository ready — ask questions now.");
      }
    } catch {}
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
          setMessages((prev) => {
            if (prev.some((m) => m.role === "assistant")) return prev;
            return [
              ...prev,
              {
                id: Date.now(),
                role: "assistant",
                content: "The repository is ready. Ask me anything about the codebase.",
              },
            ];
          });
          await loadConversations();
        }
      } catch {
        setProgress((p) => Math.min(96, p + 2));
      }
    }, 2000);
  }, [stopPolling]);

  async function handleProcess(repoUrl) {
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
    try {
      const res = await fetch(`/api/conversations/${convId}`);
      const data = await res.json();
      setMessages(
        (data.messages || []).map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
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

  async function submitMessage(e) {
    e.preventDefault();
    if (!draft.trim() || !chatEnabled) return;

    const userMsg = draft.trim();
    setDraft("");
    setMessages((prev) => [
      ...prev,
      { id: Date.now(), role: "user", content: userMsg },
    ]);

    const placeholderId = Date.now() + 1;
    setMessages((prev) => [
      ...prev,
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
      <div className="flex flex-col h-full">
        {phase === "ready" ? (
          <>
            <div className="border-b-2 border-base-300 px-6 py-3 flex items-center justify-between">
              <h1 className="font-bold text-sm uppercase tracking-wider">
                Chat
              </h1>
              <span className="font-mono text-xs text-primary uppercase">
                {chatEnabled ? "READY" : "WAITING"}
              </span>
            </div>

            <ChatMessages messages={messages} streaming={streaming} />

            <form
              onSubmit={submitMessage}
              className="border-t-2 border-base-300 p-4"
            >
              <div className="join w-full max-w-4xl mx-auto">
                <input
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder={
                    chatEnabled
                      ? "Ask about the repository..."
                      : "Processing must complete first"
                  }
                  className="input input-bordered join-item w-full font-mono text-sm"
                  disabled={!chatEnabled}
                />
                <button
                  type="submit"
                  className="btn join-item"
                  disabled={!chatEnabled || !draft.trim()}
                >
                  Send
                </button>
              </div>
            </form>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center p-8">
            <div className="w-full max-w-2xl mx-auto space-y-12">
              <div className="text-center space-y-2">
                <h2 className="text-3xl lg:text-5xl font-black uppercase tracking-tight">
                  Librarian <span className="text-primary">AI</span>
                </h2>
                <p className="text-base-content/50 text-xs font-mono uppercase tracking-widest">
                  [ REPOSITORY INGESTION ]
                </p>
              </div>

              {phase === "processing" ? (
                <ProgressBar progress={progress} statusText={statusText} />
              ) : (
                <RepoInput onProcess={handleProcess} disabled={phase === "processing"} />
              )}

              {phase === "idle" && conversations.length > 0 && (
                <div className="text-center">
                  <p className="text-xs font-mono uppercase tracking-wider text-base-content/40">
                    Or select a past conversation from the sidebar
                  </p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
}
