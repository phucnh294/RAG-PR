import { useEffect, useRef, useState } from "react";
import type { ChatOptions } from "../api/streaming";
import MessageBubble, { type ChatMessage } from "./MessageBubble";

const RERANK_STORAGE_KEY = "rag.rerankEnabled";
const MEMORY_STORAGE_KEY = "rag.memoryEnabled";
const MEMORY_TURNS_STORAGE_KEY = "rag.memoryTurns";
// Mirrors the backend defaults (MEMORY_TURNS_DEFAULT / MEMORY_MAX_TURNS); the backend
// clamps anything above its own maximum.
const DEFAULT_MEMORY_TURNS = 3;
const MAX_MEMORY_TURNS = 10;

function readStored(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function store(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage blocked (private mode): the setting still holds for this page load.
  }
}

function clampTurns(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_MEMORY_TURNS;
  return Math.min(MAX_MEMORY_TURNS, Math.max(1, Math.round(value)));
}

interface ChatWindowProps {
  title: string | null;
  messages: ChatMessage[];
  isStreaming: boolean;
  isLoading: boolean;
  error: string | null;
  onSend: (question: string, options: ChatOptions) => void;
}

/** One conversation's view; the conversation itself (and its streaming) lives in ChatPage. */
export default function ChatWindow({
  title,
  messages,
  isStreaming,
  isLoading,
  error,
  onSend,
}: ChatWindowProps) {
  const [input, setInput] = useState("");
  const [rerankEnabled, setRerankEnabled] = useState(() => readStored(RERANK_STORAGE_KEY) === "true");
  // Memory defaults ON (like the backend): only an explicit "false" turns it off.
  const [memoryEnabled, setMemoryEnabled] = useState(() => readStored(MEMORY_STORAGE_KEY) !== "false");
  const [memoryTurns, setMemoryTurns] = useState(() =>
    clampTurns(Number(readStored(MEMORY_TURNS_STORAGE_KEY) ?? DEFAULT_MEMORY_TURNS)),
  );
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
    store(RERANK_STORAGE_KEY, String(enabled));
  }

  function handleMemoryChange(enabled: boolean) {
    setMemoryEnabled(enabled);
    store(MEMORY_STORAGE_KEY, String(enabled));
  }

  function handleMemoryTurnsChange(value: number) {
    const turns = clampTurns(value);
    setMemoryTurns(turns);
    store(MEMORY_TURNS_STORAGE_KEY, String(turns));
  }

  const blocked = isStreaming || isLoading;

  function handleSend() {
    const question = input.trim();
    if (!question || blocked) return;
    setInput("");
    onSend(question, { rerank: rerankEnabled, memoryEnabled, memoryTurns });
  }

  return (
    <div className="chat-window">
      {title && <h3 className="chat-title">{title}</h3>}
      <div className="message-list" ref={listRef}>
        {error && <p className="error">{error}</p>}
        {isLoading && <p className="empty-hint">Loading conversation…</p>}
        {!isLoading && messages.length === 0 && (
          <p className="empty-hint">Ask something about the seeded documents, e.g. "how many days of leave do I get?"</p>
        )}
        {messages.map((message, index) => (
          <MessageBubble key={index} message={message} />
        ))}
      </div>
      <div className="chat-options-row">
        <label className="chat-options">
          <input
            type="checkbox"
            checked={rerankEnabled}
            onChange={(e) => handleRerankChange(e.target.checked)}
          />
          Rerank results with cross-encoder (ms-marco-MiniLM)
        </label>
        <label className="chat-options">
          <input
            type="checkbox"
            checked={memoryEnabled}
            onChange={(e) => handleMemoryChange(e.target.checked)}
          />
          Conversation memory
        </label>
        <label className="chat-options" title="How many previous question/answer turns the model sees">
          last
          <input
            className="memory-turns"
            type="number"
            min={1}
            max={MAX_MEMORY_TURNS}
            value={memoryTurns}
            disabled={!memoryEnabled}
            onChange={(e) => handleMemoryTurnsChange(e.target.valueAsNumber)}
          />
          turns
        </label>
      </div>
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
          disabled={blocked}
        />
        <button type="submit" disabled={blocked || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
