import MessageContent from "./MessageContent";
import { IconChat } from "../icons/Icon";

const DIVIDER_TEXT =
  "Repository synced — messages above reference a prior commit; messages below reference the current commit.";

const SKELETON_ROWS = [0, 1, 2, 3, 4, 5];

export default function ChatMessages({
  messages,
  streaming,
  onCitationClick,
  repoHash,
  loading,
}) {
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

  // Rendered newest-first (flex-col-reverse anchors the newest at the bottom
  // with the browser's default scroll position, so opening a chat lands on the
  // latest messages with no scroll JS and stays pinned while streaming).
  const items = [];
  for (let ri = 0; ri < messages.length; ri++) {
    const mi = messages.length - 1 - ri;
    const msg = messages[mi];
    if (dividerIdx >= 0 && mi === dividerIdx + 1) {
      items.push(
        <div key={`divider-${mi}`} className="divider my-4 text-xs text-base-content/50">
          {DIVIDER_TEXT}
        </div>
      );
    }
    items.push(
      <div key={msg.id}>
        <div className={`chat ${msg.role === "user" ? "chat-end" : "chat-start"}`}>
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
    );
  }
  if (dividerIdx >= 0 && dividerIdx === messages.length - 1) {
    items.unshift(
      <div key="divider-trailing" className="divider my-4 text-xs text-base-content/50">
        {DIVIDER_TEXT}
      </div>
    );
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col-reverse gap-3 overflow-y-auto p-4 bg-base-100">
      {loading ? (
        SKELETON_ROWS.map((i) => (
          <div key={i} className={`chat ${i % 2 ? "chat-end" : "chat-start"}`}>
            <div className={`skeleton ${i % 2 ? "w-1/2" : "w-2/3"} h-12 rounded-2xl`} />
          </div>
        ))
      ) : messages.length === 0 && !streaming ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <IconChat className="w-8 h-8 mx-auto mb-3 text-base-content/40" />
            <p className="text-lg font-semibold text-base-content/70">
              Ready to chat
            </p>
            <p className="mt-1.5 text-sm text-base-content/40">
              Ask anything about the repository
            </p>
          </div>
        </div>
      ) : (
        items
      )}
    </div>
  );
}
