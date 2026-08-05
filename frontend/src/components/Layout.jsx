import Sidebar from "./Sidebar";

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

  return (
    <div className="drawer lg:drawer-open min-h-screen">
      <input id={drawerId} type="checkbox" className="drawer-toggle" />

      <div className="drawer-content flex flex-col min-h-screen overflow-hidden">
        <label
          htmlFor={drawerId}
          className="btn btn-ghost drawer-button lg:hidden fixed top-2 left-2 z-50"
        >
          ☰
        </label>
        <main className="flex-1 flex flex-col">{children}</main>
      </div>

      <div className="drawer-side min-h-screen">
        <label htmlFor={drawerId} aria-label="close sidebar" className="drawer-overlay" />
        <div className="w-72 min-h-screen">
          <Sidebar
            conversations={conversations}
            activeConvId={activeConvId}
            onSelect={(id) => {
              onSelectConversation(id);
              document.getElementById(drawerId).checked = false;
            }}
            onNewChat={onNewChat}
            onDelete={onDeleteConversation}
            loading={conversationsLoading}
          />
        </div>
      </div>
    </div>
  );
}
