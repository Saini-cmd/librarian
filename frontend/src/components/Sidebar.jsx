import { useAuth } from "@clerk/clerk-react";
import { useNavigate } from "react-router-dom";
import { IconAdd, IconTrash, IconSettings, IconExit } from "../icons/Icon";

export default function Sidebar({
  conversations,
  activeConvId,
  onSelect,
  onNewChat,
  onDelete,
  loading,
  collapsed,
}) {
  const { signOut } = useAuth();
  const navigate = useNavigate();

  return (
    <aside className="flex flex-col flex-1 min-h-0">
      <div className={`flex justify-center pb-3 ${collapsed ? "" : "px-3"}`}>
        {collapsed ? (
          <button
            className="btn btn-circle btn-primary"
            onClick={onNewChat}
            title="Ingest New Repo"
          >
            <IconAdd className="w-4 h-4" />
          </button>
        ) : (
          <button
            className="btn btn-primary btn-block rounded-full font-medium"
            onClick={onNewChat}
          >
            <IconAdd className="w-4 h-4" />
            Ingest New Repo
          </button>
        )}
      </div>

      {!collapsed && (
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
                        className="btn btn-ghost btn-sm btn-circle text-base-content/80 hover:text-error"
                        onClick={(e) => {
                          e.stopPropagation();
                          onDelete(conv.id);
                        }}
                      >
                        <IconTrash className="w-3.5 h-3.5" />
                      </button>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </nav>
      )}

      {collapsed && <div className="flex-1" />}

      <div className="px-3 py-3 border-t border-base-content/10">
        {collapsed ? (
          <div className="flex flex-col items-center gap-1 -mx-3">
            <button
              className="btn btn-neutral btn-circle"
              onClick={() => navigate("/settings")}
              title="Settings"
            >
              <IconSettings className="w-4 h-4" />
            </button>
            <button
              className="btn btn-error btn-circle"
              onClick={() => signOut()}
              title="Sign Out"
            >
              <IconExit className="w-4 h-4" />
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            <button
              className="btn btn-neutral btn-block rounded-full"
              onClick={() => navigate("/settings")}
            >
              <IconSettings className="w-4 h-4" />
              Settings
            </button>
            <button
              className="btn btn-error btn-block rounded-full"
              onClick={() => signOut()}
            >
              <IconExit className="w-4 h-4" />
              Sign Out
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}
