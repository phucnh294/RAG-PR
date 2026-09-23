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

export default function App() {
  const [tab, setTab] = useState<Tab>("chat");
  const [sidebarOpen, setSidebarOpen] = useState(true);

  return (
    <div className="app">
      {sidebarOpen && (
        <aside className="sidebar">
          <h1 className="sidebar-title">RAG Assistant</h1>
          <nav className="sidebar-nav">
            {TABS.map((item) => (
              <button
                key={item.id}
                className={tab === item.id ? "active" : ""}
                onClick={() => setTab(item.id)}
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
                    onClick={() => setTab(item.id)}
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
