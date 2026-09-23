import { useState } from "react";
import ChatPage from "./pages/ChatPage";
import DocumentsPage from "./pages/DocumentsPage";
import LogsPage from "./pages/LogsPage";

type Tab = "chat" | "documents" | "logs";

const TABS: { id: Tab; label: string }[] = [
  { id: "chat", label: "Chat" },
  { id: "documents", label: "Documents" },
  { id: "logs", label: "Logs" },
];

const MOBILE_BREAKPOINT_PX = 768;

function isMobileViewport(): boolean {
  return typeof window !== "undefined" && window.innerWidth <= MOBILE_BREAKPOINT_PX;
}

export default function App() {
  const [tab, setTab] = useState<Tab>("chat");
  const [sidebarOpen, setSidebarOpen] = useState(() => !isMobileViewport());

  function selectTab(id: Tab) {
    setTab(id);
    // On a phone the sidebar is a full-screen overlay — close it once a tab is
    // picked so the user immediately sees the page instead of the drawer.
    if (isMobileViewport()) {
      setSidebarOpen(false);
    }
  }

  return (
    <div className="app">
      {sidebarOpen && (
        <div className="sidebar-backdrop" onClick={() => setSidebarOpen(false)} />
      )}
      {sidebarOpen && (
        <aside className="sidebar">
          <h1 className="sidebar-title">RAG Assistant</h1>
          <nav className="sidebar-nav">
            {TABS.map((item) => (
              <button
                key={item.id}
                className={tab === item.id ? "active" : ""}
                onClick={() => selectTab(item.id)}
              >
                {item.label}
              </button>
            ))}
          </nav>
        </aside>
      )}
      <main className="content">
        <div className="content-topbar">
          <button
            className="sidebar-toggle"
            onClick={() => setSidebarOpen((open) => !open)}
            aria-label={sidebarOpen ? "Hide panel" : "Show panel"}
            title={sidebarOpen ? "Hide panel" : "Show panel"}
          >
            {sidebarOpen ? "«" : "»"}
          </button>
          {!sidebarOpen && (
            <>
              <span className="content-title">RAG Assistant</span>
              <nav className="topbar-nav">
                {TABS.map((item) => (
                  <button
                    key={item.id}
                    className={tab === item.id ? "active" : ""}
                    onClick={() => selectTab(item.id)}
                  >
                    {item.label}
                  </button>
                ))}
              </nav>
            </>
          )}
        </div>
        {tab === "chat" && <ChatPage />}
        {tab === "documents" && <DocumentsPage />}
        {tab === "logs" && <LogsPage />}
      </main>
    </div>
  );
}
