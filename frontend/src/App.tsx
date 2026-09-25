import { Fragment, useEffect, useState } from "react";
import { fetchDemoUsers, type UserOut } from "./api/client";
import { getSelectedUserId, setSelectedUserId } from "./auth/identity";
import RoleSelector from "./components/RoleSelector";
import ChatPage from "./pages/ChatPage";
import DocumentsPage from "./pages/DocumentsPage";
import EvalsPage from "./pages/EvalsPage";
import LogsPage from "./pages/LogsPage";

type Tab = "chat" | "documents" | "logs" | "evals";

const TABS: { id: Tab; label: string }[] = [
  { id: "chat", label: "Chat" },
  { id: "documents", label: "Documents" },
  { id: "logs", label: "Logs" },
  { id: "evals", label: "Evals" },
];

const MOBILE_BREAKPOINT_PX = 768;

function isMobileViewport(): boolean {
  return typeof window !== "undefined" && window.innerWidth <= MOBILE_BREAKPOINT_PX;
}

export default function App() {
  const [tab, setTab] = useState<Tab>("chat");
  const [sidebarOpen, setSidebarOpen] = useState(() => !isMobileViewport());
  const [users, setUsers] = useState<UserOut[]>([]);
  const [userId, setUserId] = useState<string | null>(null);
  const [identityError, setIdentityError] = useState<string | null>(null);

  useEffect(() => {
    fetchDemoUsers()
      .then((loaded) => {
        setUsers(loaded);
        // Keep a remembered choice only if that user still exists; otherwise act as admin.
        const remembered = loaded.find((user) => user.id === getSelectedUserId());
        const initial = remembered ?? loaded.find((user) => user.role === "admin") ?? loaded[0];
        if (initial) selectUser(initial.id);
      })
      .catch((err) =>
        setIdentityError(err instanceof Error ? err.message : "Failed to load users"),
      );
  }, []);

  function selectUser(id: string) {
    setSelectedUserId(id);
    setUserId(id);
  }

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
          <RoleSelector users={users} selectedUserId={userId} onSelect={selectUser} />
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
        {identityError && <p className="error">{identityError}</p>}
        {/* Every page stays mounted and inactive ones are only hidden, so switching tabs
            keeps each page's state (chat history, filters, eval reports, an answer still
            streaming). Keyed by user: switching identity remounts them as that user. */}
        {userId && (
          <Fragment key={userId}>
            <div hidden={tab !== "chat"}>
              <ChatPage userId={userId} />
            </div>
            <div hidden={tab !== "documents"}>
              <DocumentsPage active={tab === "documents"} />
            </div>
            <div hidden={tab !== "logs"}>
              <LogsPage active={tab === "logs"} />
            </div>
            <div hidden={tab !== "evals"}>
              <EvalsPage />
            </div>
          </Fragment>
        )}
      </main>
    </div>
  );
}
