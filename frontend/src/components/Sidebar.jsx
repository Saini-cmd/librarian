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
    <aside className="flex flex-col min-h-screen bg-base-200 border-r-2 border-base-300">
      <div className="p-4 border-b-2 border-base-300">
        <h2 className="font-bold text-base-content text-lg tracking-tight uppercase">
          Librarian
        </h2>
      </div>

      <div className="p-3 border-b-2 border-base-300">
        <button
          className="btn btn-block btn-outline btn-sm"
          onClick={onNewChat}
        >
          + New Chat
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="p-4 space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="skeleton h-8 w-full" />
            ))}
          </div>
        ) : conversations.length === 0 ? (
          <p className="text-base-content/50 text-xs text-center p-4 uppercase tracking-widest">
            No conversations
          </p>
        ) : (
          <ul className="menu menu-sm p-2">
            {conversations.map((conv) => (
              <li key={conv.id}>
                <button
                  className={`flex items-center justify-between w-full ${
                    activeConvId === conv.id ? "menu-active" : ""
                  }`}
                  onClick={() => onSelect(conv.id)}
                >
                  <span className="truncate flex-1 text-left">
                    {conv.title || conv.repo_name}
                  </span>
                  <button
                    className="btn btn-ghost btn-xs btn-square text-base-content/40 hover:text-error"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(conv.id);
                    }}
                  >
                    X
                  </button>
                </button>
              </li>
            ))}
          </ul>
        )}
      </nav>

      <div className="p-3 border-t-2 border-base-300 space-y-2">
        <button
          className="btn btn-ghost btn-sm btn-block justify-start text-xs uppercase tracking-wider"
          onClick={() => navigate("/settings")}
        >
          Settings
        </button>
        <button
          className="btn btn-ghost btn-sm btn-block justify-start text-xs uppercase tracking-wider text-base-content/60"
          onClick={() => signOut()}
        >
          Sign Out
        </button>
      </div>
    </aside>
  );
}
