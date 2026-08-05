import { useEffect, useRef } from "react";
import MessageContent from "./MessageContent";

export default function ChatMessages({ messages, streaming }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      {messages.length === 0 && !streaming && (
        <p className="text-base-content/40 text-xs uppercase tracking-widest text-center pt-16">
          Ask a question about the repository
        </p>
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
            <MessageContent role={msg.role} content={msg.content} />
          </div>
        </div>
      ))}

      {streaming && (
        <div className="chat chat-start">
          <div className="chat-bubble bg-base-300 rounded-none">
            <span className="loading loading-dots loading-sm" />
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
