import { useState } from "react";
import Sidebar from "./Sidebar";
import { IconMenu, IconClose, IconChevronsLeft } from "../icons/Icon";

export default function Layout({
  conversations,
  activeConvId,
  onSelectConversation,
  onNewChat,
  onDeleteConversation,
  conversationsLoading,
  children,
}) {
  const drawerId = "app-drawer";
  const [drawerOpen, setDrawerOpen] = useState(() =>
    typeof window !== "undefined" &&
    window.matchMedia("(min-width: 1024px)").matches
  );

  function closeDrawer() {
    if (typeof window !== "undefined" && window.matchMedia("(min-width: 1024px)").matches) return;
    setDrawerOpen(false);
  }

  return (
    <div className="drawer lg:drawer-open min-h-screen">
      <input
        id={drawerId}
        type="checkbox"
        className="drawer-toggle"
        checked={drawerOpen}
        onChange={(e) => setDrawerOpen(e.target.checked)}
      />

      <div className="drawer-content flex flex-col min-h-screen overflow-hidden bg-base-100">
        {!drawerOpen && (
          <label
            htmlFor={drawerId}
            className="btn btn-ghost drawer-button lg:hidden fixed top-2 left-2 z-50"
            aria-label="Open menu"
          >
            <IconMenu className="w-5 h-5" />
          </label>
        )}
        <main className="flex-1 flex flex-col min-h-0">{children}</main>
      </div>

      <div className="drawer-side min-h-screen">
        <label htmlFor={drawerId} aria-label="close sidebar" className="drawer-overlay" />
        <div className="flex h-dvh flex-col overflow-hidden glass-surface border-r border-base-content/10 w-14 is-drawer-open:w-64 lg:is-drawer-open:w-80 transition-all">
          <div
            className={`flex items-center px-3 py-3 ${
              drawerOpen ? "justify-between" : "justify-center"
            }`}
          >
            <h2 className="text-lg font-semibold tracking-tight text-base-content is-drawer-close:hidden">
              Librarian
            </h2>
            <div className="flex items-center gap-1">
              <label
                htmlFor={drawerId}
                className="btn btn-ghost btn-circle btn-sm hidden lg:inline-flex"
                aria-label={drawerOpen ? "Collapse sidebar" : "Expand sidebar"}
              >
                <IconChevronsLeft
                  className={`w-4 h-4 transition-transform ${drawerOpen ? "" : "rotate-180"}`}
                />
              </label>
              <label
                htmlFor={drawerId}
                className="btn btn-ghost btn-circle btn-sm lg:hidden"
                aria-label="Close sidebar"
              >
                <IconClose className="w-6 h-6" />
              </label>
            </div>
          </div>
          <Sidebar
            collapsed={!drawerOpen}
            conversations={conversations}
            activeConvId={activeConvId}
            onSelect={(id) => {
              onSelectConversation(id);
              closeDrawer();
            }}
            onNewChat={() => {
              onNewChat();
              closeDrawer();
            }}
            onDelete={(id) => {
              onDeleteConversation(id);
              closeDrawer();
            }}
            loading={conversationsLoading}
          />
        </div>
      </div>
    </div>
  );
}
