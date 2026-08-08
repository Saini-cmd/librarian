import { useEffect, useRef } from "react";
import MessageContent from "./MessageContent";

export default function ChatMessages({ messages, streaming, onCitationClick }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

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

      {messages.map((msg) => (
        <div
          key={msg.id}
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
      ))}

      <div ref={bottomRef} />
    </div>
  );
}
