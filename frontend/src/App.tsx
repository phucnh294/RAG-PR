import { useState } from "react";
import ChatPage from "./pages/ChatPage";
import DocumentsPage from "./pages/DocumentsPage";

type Tab = "chat" | "documents";

export default function App() {
  const [tab, setTab] = useState<Tab>("chat");

  return (
    <div className="app">
      <header className="app-header">
        <h1>RAG Assistant</h1>
        <nav className="tabs">
          <button className={tab === "chat" ? "active" : ""} onClick={() => setTab("chat")}>
            Chat
          </button>
          <button
            className={tab === "documents" ? "active" : ""}
            onClick={() => setTab("documents")}
          >
            Documents
          </button>
        </nav>
      </header>
      <main>{tab === "chat" ? <ChatPage /> : <DocumentsPage />}</main>
    </div>
  );
}
