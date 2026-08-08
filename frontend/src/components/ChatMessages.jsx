import { useEffect, useRef } from "react";
import MessageContent from "./MessageContent";

const DIVIDER_TEXT =
  "Repository synced — messages above reference a prior commit; messages below reference the current commit.";

export default function ChatMessages({ messages, streaming, onCitationClick, repoHash }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  // Sync-boundary: a divider renders after the last message whose commit hash
  // differs from the conversation's current commit. This shows immediately
  // after a sync (before any new-commit message exists) and survives refresh.
  let dividerIdx = -1;
  if (repoHash) {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].repo_hash && messages[i].repo_hash !== repoHash) {
        dividerIdx = i;
        break;
      }
    }
  }

  return (
    <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3 bg-base-100">
      {messages.length === 0 && !streaming && (
        <div className="min-h-full flex items-center justify-center">
          <div className="text-center">
            <p className="text-lg font-semibold text-base-content/70">
              Ready to chat
            </p>
            <p className="mt-1.5 text-sm text-base-content/40">
              Ask anything about the repository
            </p>
          </div>
        </div>
      )}

      {messages.map((msg, idx) => (
        <div key={msg.id}>
          {idx === dividerIdx + 1 && (
            <div className="divider my-4 text-xs text-base-content/50">
              {DIVIDER_TEXT}
            </div>
          )}
          <div
            className={`chat ${msg.role === "user" ? "chat-end" : "chat-start"}`}
          >
            <div
              className={`chat-bubble text-sm leading-relaxed ${
                msg.role === "user"
                  ? "chat-bubble-primary"
                  : "bg-base-200 text-base-content"
              }`}
            >
              {msg.role === "assistant" && msg.content === "" && streaming ? (
                <span className="loading loading-dots loading-sm" />
              ) : (
                <MessageContent
                  role={msg.role}
                  content={msg.content}
                  citations={msg.citations}
                  onCitationClick={onCitationClick}
                />
              )}
            </div>
          </div>
        </div>
      ))}

      {dividerIdx === messages.length - 1 && (
        <div className="divider my-4 text-xs text-base-content/50">
          {DIVIDER_TEXT}
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
