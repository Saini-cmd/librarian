import { useAuth } from "@clerk/clerk-react";
import { useNavigate } from "react-router-dom";

export default function Sidebar({
  conversations,
  activeConvId,
  onSelect,
  onNewChat,
  onDelete,
  loading,
}) {
  const { signOut } = useAuth();
  const navigate = useNavigate();

  return (
    <aside className="flex flex-col h-full">
      <div className="px-5 pt-5 pb-3">
        <h2 className="text-lg font-semibold tracking-tight text-base-content">
          Librarian
        </h2>
      </div>

      <div className="px-4 pb-3">
        <button
          className="btn btn-primary btn-block rounded-full font-medium"
          onClick={onNewChat}
        >
          + Ingest New Repo
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 pb-3">
        {loading ? (
          <div className="px-2 space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="skeleton h-10 w-full rounded-xl" />
            ))}
          </div>
        ) : conversations.length === 0 ? (
          <p className="text-base-content/40 text-sm text-center px-4 pt-8">
            No conversations yet
          </p>
        ) : (
          <ul className="space-y-1">
            {conversations.map((conv) => {
              const active = activeConvId === conv.id;
              return (
                <li key={conv.id}>
                  <button
                    className={`w-full flex items-center justify-between gap-2 rounded-xl px-3 py-2.5 text-left text-sm transition-colors ${
                      active
                        ? "bg-primary/10 text-primary font-medium"
                        : "text-base-content/80 hover:bg-base-content/5"
                    }`}
                    onClick={() => onSelect(conv.id)}
                  >
                    <span className="truncate flex-1">
                      {conv.title || conv.repo_name}
                    </span>
                    <button
                      className="btn btn-ghost btn-xs btn-circle text-base-content/30 hover:text-error"
                      onClick={(e) => {
                        e.stopPropagation();
                        onDelete(conv.id);
                      }}
                    >
                      X
                    </button>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </nav>

      <div className="px-3 py-3 border-t border-base-content/10 space-y-1">
        <button
          className="btn btn-ghost btn-sm btn-block justify-start rounded-lg font-normal"
          onClick={() => navigate("/settings")}
        >
          Settings
        </button>
        <button
          className="btn btn-ghost btn-sm btn-block justify-start rounded-lg font-normal text-base-content/60"
          onClick={() => signOut()}
        >
          Sign Out
        </button>
      </div>
    </aside>
  );
}
