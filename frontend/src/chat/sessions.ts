// Chat sessions live only in the browser: the backend answers each message on its own
// (no conversation memory), so a session is this UI's history of one conversation.
// Saved per user in localStorage, so switching role shows that user's chats and a
// reload keeps them.

import type { ChatMessage } from "../components/MessageBubble";

export interface ChatSession {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: ChatMessage[];
}

const STORAGE_PREFIX = "rag.chatSessions.";
// Citations carry full chunk excerpts, so cap history to stay well inside the ~5 MB
// localStorage quota; the least recently used sessions are dropped first.
const MAX_SESSIONS = 30;
const TITLE_LENGTH = 48;
export const NEW_CHAT_TITLE = "New chat";

function storageKey(userId: string): string {
  return `${STORAGE_PREFIX}${userId}`;
}

function newId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function createSession(): ChatSession {
  const now = Date.now();
  return { id: newId(), title: NEW_CHAT_TITLE, createdAt: now, updatedAt: now, messages: [] };
}

export function titleFromQuestion(question: string): string {
  const oneLine = question.replace(/\s+/g, " ").trim();
  return oneLine.length > TITLE_LENGTH ? `${oneLine.slice(0, TITLE_LENGTH - 1)}…` : oneLine;
}

export function loadSessions(userId: string): ChatSession[] {
  try {
    const raw = window.localStorage.getItem(storageKey(userId));
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return (parsed as ChatSession[]).filter(
      (session) => typeof session?.id === "string" && Array.isArray(session.messages),
    );
  } catch {
    return [];
  }
}

export function saveSessions(userId: string, sessions: ChatSession[]): void {
  const kept = [...sessions]
    .filter((session) => session.messages.length > 0)
    .sort((a, b) => b.updatedAt - a.updatedAt)
    .slice(0, MAX_SESSIONS);
  try {
    window.localStorage.setItem(storageKey(userId), JSON.stringify(kept));
  } catch {
    // Storage blocked or full: sessions still work for this page load.
  }
}
