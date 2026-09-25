import { useEffect, useRef, useState } from "react";
import type { ChatOptions } from "../api/streaming";
import MessageBubble, { type ChatMessage } from "./MessageBubble";

const RERANK_STORAGE_KEY = "rag.rerankEnabled";

function readStoredRerank(): boolean {
  try {
    return window.localStorage.getItem(RERANK_STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

function storeRerank(enabled: boolean): void {
  try {
    window.localStorage.setItem(RERANK_STORAGE_KEY, String(enabled));
  } catch {
    // Storage blocked (private mode): the toggle still holds for this page load.
  }
}

interface ChatWindowProps {
  title: string | null;
  messages: ChatMessage[];
  isStreaming: boolean;
  onSend: (question: string, options: ChatOptions) => void;
}

/** One conversation's view; the conversation itself (and its streaming) lives in ChatPage. */
export default function ChatWindow({ title, messages, isStreaming, onSend }: ChatWindowProps) {
  const [input, setInput] = useState("");
  const [rerankEnabled, setRerankEnabled] = useState(readStoredRerank);
  const listRef = useRef<HTMLDivElement>(null);
  const lastContent = messages[messages.length - 1]?.content;

  // Follow the conversation: jump to the latest message when switching chats, sending,
  // or while an answer streams in.
  useEffect(() => {
    const list = listRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [messages.length, lastContent]);

  function handleRerankChange(enabled: boolean) {
    setRerankEnabled(enabled);
    storeRerank(enabled);
  }

  function handleSend() {
    const question = input.trim();
    if (!question || isStreaming) return;
    setInput("");
    onSend(question, { rerank: rerankEnabled });
  }

  return (
    <div className="chat-window">
      {title && <h3 className="chat-title">{title}</h3>}
      <div className="message-list" ref={listRef}>
        {messages.length === 0 && (
          <p className="empty-hint">Ask something about the seeded documents, e.g. "how many days of leave do I get?"</p>
        )}
        {messages.map((message, index) => (
          <MessageBubble key={index} message={message} />
        ))}
      </div>
      <label className="chat-options">
        <input
          type="checkbox"
          checked={rerankEnabled}
          onChange={(e) => handleRerankChange(e.target.checked)}
        />
        Rerank results with cross-encoder (ms-marco-MiniLM)
      </label>
      <form
        className="chat-input"
        onSubmit={(e) => {
          e.preventDefault();
          handleSend();
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={isStreaming ? "Answering… you can switch to another chat meanwhile" : "Type a message..."}
          disabled={isStreaming}
        />
        <button type="submit" disabled={isStreaming || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
