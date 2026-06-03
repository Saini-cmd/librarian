import { useMemo, useState, useEffect, useRef } from 'react';

const stages = [
  { key: 'ingest', label: 'Ingesting repo' },
  { key: 'scan', label: 'Scanning files' },
  { key: 'chunk', label: 'Chunking code' },
  { key: 'embed', label: 'Embedding chunks' },
  { key: 'ready', label: 'Ready for chat' },
];

const sampleMessages = [
  {
    id: 1,
    role: 'assistant',
    content: 'Run the pipeline first. I will unlock the chat panel once the repository has been processed.',
  },
];

function App() {
  const [repoLink, setRepoLink] = useState('');
  const [mode, setMode] = useState('local');
  const [phase, setPhase] = useState('idle');
  const [statusText, setStatusText] = useState('Paste a repository link to begin.');
  const [progress, setProgress] = useState(0);
  const [chatEnabled, setChatEnabled] = useState(false);
  const [messages, setMessages] = useState(sampleMessages);
  const [draft, setDraft] = useState('');

  const currentStage = useMemo(() => {
    if (phase === 'processing') {
      if (progress < 20) return stages[0];
      if (progress < 40) return stages[1];
      if (progress < 70) return stages[2];
      if (progress < 100) return stages[3];
    }

    if (phase === 'ready') return stages[4];
    return null;
  }, [phase, progress]);

  const startPipeline = () => {
    if (phase === 'processing') return;

    if (!repoLink.trim()) {
      setStatusText('Paste a repository link first.');
      return;
    }

    setPhase('processing');
    setChatEnabled(false);
    setProgress(6);
    setStatusText('Starting pipeline — cloning repository...');

    // Start server-side processing
    window
      .fetch('/api/process', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ repo_url: repoLink.trim(), mode }),
      })
      .then(async (response) => {
        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(errorText || 'Pipeline request failed');
        }

        return response.json();
      })
      .then((data) => {
        // server accepted and will process; rely on /api/status polling for readiness
        setStatusText(data.message || 'Repository processing started.');
      })
      .catch((error) => {
        setPhase('idle');
        setProgress(0);
        setStatusText(`Pipeline failed to start: ${error.message}`);
        setMessages((current) => [
          ...current,
          {
            id: Date.now(),
            role: 'assistant',
            content: 'Pipeline failed to start. Please check the backend and try again.',
          },
        ]);
      });

    // begin polling status endpoint to update progress/stage
    startPollingStatus();
  };

  const pollRef = useRef(null);

  const startPollingStatus = () => {
    if (pollRef.current) return;

    pollRef.current = window.setInterval(async () => {
      try {
        const res = await fetch('/api/status');
        if (!res.ok) throw new Error('Status fetch failed');
        const data = await res.json();

        // Interpret server response if it provides helpful fields
        if (data.progress !== undefined) setProgress(data.progress);
        if (data.stage) setStatusText(data.stage);

        // Fallback gentle progress when no numeric progress provided
        if (data.progress === undefined) {
          setProgress((p) => Math.min(98, Math.max(p + 4, 12)));
        }

        // Only the backend's ready flag should unlock chat.
        const ready = data.ready === true || data.phase === 'ready';
        if (ready) {
          window.clearInterval(pollRef.current);
          pollRef.current = null;
          setProgress(100);
          setPhase('ready');
          setChatEnabled(true);
          setStatusText(data.message || 'Repository ready — you can ask questions now.');
          setMessages((current) => [
            ...current,
            {
              id: Date.now(),
              role: 'assistant',
              content: 'The repository is ready. Ask me anything about the codebase.',
            },
          ]);
        }
      } catch (err) {
        // polling errors — show a gentle note but keep trying
        setStatusText((s) => (s.includes('failed') ? s : 'Processing — awaiting backend updates...'));
        setProgress((p) => Math.min(96, p + 2));
      }
    }, 1000);
  };

  useEffect(() => {
    return () => {
      if (pollRef.current) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, []);

  const submitMessage = (event) => {
    event.preventDefault();
    if (!draft.trim()) return;

    const userMessage = draft.trim();
    setMessages((current) => [...current, { id: Date.now(), role: 'user', content: userMessage }]);
    setDraft('');

    window
      .fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message: userMessage, mode }),
      })
      .then(async (response) => {
        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(errorText || 'Chat request failed');
        }

        return response.json();
      })
      .then((data) => {
        setMessages((current) => [
          ...current,
          { id: Date.now() + 1, role: 'assistant', content: data.answer },
        ]);
      })
      .catch((error) => {
        setMessages((current) => [
          ...current,
          {
            id: Date.now() + 1,
            role: 'assistant',
            content: `Chat failed: ${error.message}`,
          },
        ]);
      });
  };

  return (
    <div className="app-shell">
      <div className="bg-orb bg-orb-one" />
      <div className="bg-orb bg-orb-two" />

      <main className="layout">
        {phase === 'ready' ? (
          <section className={`screen-panel chat-panel ${chatEnabled ? 'chat-panel-ready' : 'chat-panel-disabled'}`}>
            <div className="chat-header">
              <h2>Chat</h2>
              <span>{chatEnabled ? 'Ready' : 'Waiting for processing'}</span>
            </div>

            <div className="chat-stream">
              {messages.map((message) => (
                <div key={message.id} className={`message message-${message.role}`}>
                  {message.content}
                </div>
              ))}
            </div>

            <form className="chat-form" onSubmit={submitMessage}>
              <input
                disabled={!chatEnabled}
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder={chatEnabled ? 'Ask about the repository...' : 'Processing must complete first'}
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
                Unleash the power of AI to navigate and understand your codebase like never before!
              </p>
            </div>

            <div className="input-row clean-input-row">
              <input
                id="repo-link"
                value={repoLink}
                onChange={(event) => setRepoLink(event.target.value)}
                placeholder="Paste GitHub repo URL"
              />
              <select value={mode} onChange={(e) => setMode(e.target.value)} style={{ marginRight: 8 }}>
                <option value="local">Local (Ollama)</option>
                <option value="external">External (Gemini)</option>
              </select>

              <button type="button" onClick={startPipeline} disabled={phase === 'processing'}>
                {phase === 'processing' ? 'Processing…' : 'Process repository'}
              </button>
            </div>

            {phase === 'processing' && (
              <div className="progress-row">
                <div className="progress-header">
                  <span className="status-text">{statusText}</span>
                </div>
                <div className="progress-track" aria-label="pipeline progress">
                  <div className="progress-fill" style={{ width: `${progress}%` }} />
                </div>
                <div className="progress-footnote">{Math.round(progress)}% complete</div>
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  );
}

export default App;
