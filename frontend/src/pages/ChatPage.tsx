import { useEffect, useState } from "react";
import { streamChat, type ChatOptions } from "../api/streaming";
import {
  createSession,
  loadSessions,
  NEW_CHAT_TITLE,
  saveSessions,
  titleFromQuestion,
  type ChatSession,
} from "../chat/sessions";
import ChatSessionList from "../components/ChatSessionList";
import ChatWindow from "../components/ChatWindow";
import type { ChatMessage } from "../components/MessageBubble";

interface ChatPageProps {
  userId: string;
}

function initialSessions(userId: string): ChatSession[] {
  const stored = loadSessions(userId);
  return stored.length > 0 ? stored : [createSession()];
}

function mostRecent(sessions: ChatSession[]): ChatSession {
  return sessions.reduce((latest, session) =>
    session.updatedAt > latest.updatedAt ? session : latest,
  );
}

export default function ChatPage({ userId }: ChatPageProps) {
  const [sessions, setSessions] = useState<ChatSession[]>(() => initialSessions(userId));
  const [activeId, setActiveId] = useState<string>(() => mostRecent(sessions).id);
  const [streamingIds, setStreamingIds] = useState<ReadonlySet<string>>(new Set());

  const activeSession = sessions.find((session) => session.id === activeId) ?? sessions[0];
  const anyStreaming = streamingIds.size > 0;

  // Persist once answers finish, not on every streamed token.
  useEffect(() => {
    if (!anyStreaming) saveSessions(userId, sessions);
  }, [userId, sessions, anyStreaming]);

  function updateSession(id: string, update: (session: ChatSession) => ChatSession) {
    setSessions((prev) => prev.map((session) => (session.id === id ? update(session) : session)));
  }

  // Tokens and the payload always land in the session that asked, even if the user has
  // switched to another chat while the answer is still streaming.
  function updateLastMessage(id: string, update: (message: ChatMessage) => ChatMessage) {
    updateSession(id, (session) => {
      const messages = [...session.messages];
      messages[messages.length - 1] = update(messages[messages.length - 1]);
      return { ...session, messages, updatedAt: Date.now() };
    });
  }

  function setStreaming(id: string, streaming: boolean) {
    setStreamingIds((prev) => {
      const next = new Set(prev);
      if (streaming) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  async function handleSend(question: string, options: ChatOptions) {
    const sessionId = activeSession.id;
    updateSession(sessionId, (session) => ({
      ...session,
      title: session.messages.length === 0 ? titleFromQuestion(question) : session.title,
      updatedAt: Date.now(),
      messages: [
        ...session.messages,
        { role: "user", content: question },
        { role: "assistant", content: "" },
      ],
    }));
    setStreaming(sessionId, true);

    try {
      await streamChat(
        question,
        options,
        (token) =>
          updateLastMessage(sessionId, (last) => ({ ...last, content: last.content + token })),
        (payload) =>
          updateLastMessage(sessionId, (last) => ({
            ...last,
            citations: payload.citations,
            guardrails: payload.guardrails,
            evidence: payload.evidence,
            retrieval: payload.retrieval,
          })),
      );
    } catch (error) {
      updateLastMessage(sessionId, () => ({
        role: "assistant",
        content: `Error: ${error instanceof Error ? error.message : "chat request failed"}`,
      }));
    } finally {
      setStreaming(sessionId, false);
    }
  }

  function handleCreate() {
    // Reuse an untouched chat instead of piling up empty "New chat" entries.
    const empty = sessions.find((session) => session.messages.length === 0);
    if (empty) {
      setActiveId(empty.id);
      return;
    }
    const session = createSession();
    setSessions((prev) => [...prev, session]);
    setActiveId(session.id);
  }

  function handleDelete(id: string) {
    const remaining = sessions.filter((session) => session.id !== id);
    if (remaining.length === 0) {
      const session = createSession();
      setSessions([session]);
      setActiveId(session.id);
      return;
    }
    setSessions(remaining);
    if (id === activeId) setActiveId(mostRecent(remaining).id);
  }

  return (
    <section className="page chat-page">
      <ChatSessionList
        sessions={sessions}
        activeId={activeSession.id}
        streamingIds={streamingIds}
        onSelect={setActiveId}
        onCreate={handleCreate}
        onDelete={handleDelete}
      />
      <ChatWindow
        title={activeSession.title === NEW_CHAT_TITLE ? null : activeSession.title}
        messages={activeSession.messages}
        isStreaming={streamingIds.has(activeSession.id)}
        onSend={handleSend}
      />
    </section>
  );
}
