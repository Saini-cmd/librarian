import { useEffect, useRef } from "react";
import MessageContent from "./MessageContent";

export default function ChatMessages({ messages, streaming }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  return (
    <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4">
      {messages.length === 0 && !streaming && (
        <div className="min-h-full flex items-center justify-center">
          <div className="text-center">
            <p className="text-xl font-black uppercase tracking-tight text-base-content/80">
              Ready to chat
            </p>
            <p className="mt-2 text-base-content/40 text-xs font-mono uppercase tracking-widest">
              The repository is ingested — ask anything about the codebase
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
                ? "bg-primary text-primary-content rounded-none"
                : "bg-base-300 text-base-content rounded-none"
            }`}
          >
            {msg.role === "assistant" && msg.content === "" && streaming ? (
              <span className="loading loading-dots loading-sm" />
            ) : (
              <MessageContent role={msg.role} content={msg.content} />
            )}
          </div>
        </div>
      ))}

      <div ref={bottomRef} />
    </div>
  );
}
