import { useEffect, useState } from "react";
import { deleteConversation, fetchConversation, fetchConversations } from "../api/client";
import { streamChat, type ChatOptions } from "../api/streaming";
import {
  createDraftSession,
  messagesFromServer,
  NEW_CHAT_TITLE,
  sessionFromConversation,
  titleFromQuestion,
  type ChatSession,
} from "../chat/sessions";
import ChatSessionList from "../components/ChatSessionList";
import ChatWindow from "../components/ChatWindow";
import type { ChatMessage } from "../components/MessageBubble";

interface ChatPageProps {
  userId: string;
}

function errorText(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

// Remounted per user (App keys it by userId), so loading on mount is loading per user.
export default function ChatPage({ userId }: ChatPageProps) {
  const [initialDraft] = useState(createDraftSession);
  const [sessions, setSessions] = useState<ChatSession[]>([initialDraft]);
  const [activeId, setActiveId] = useState<string>(initialDraft.id);
  const [streamingIds, setStreamingIds] = useState<ReadonlySet<string>>(new Set());
  const [loadError, setLoadError] = useState<string | null>(null);

  const activeSession = sessions.find((session) => session.id === activeId) ?? sessions[0];

  useEffect(() => {
    let cancelled = false;
    fetchConversations()
      .then((conversations) => {
        if (cancelled || conversations.length === 0) return;
        const loaded = conversations.map(sessionFromConversation);
        // Keep the draft only if something was already typed into it meanwhile.
        setSessions((prev) => [...prev.filter((session) => session.messages.length > 0), ...loaded]);
        setActiveId((current) => (current === initialDraft.id ? loaded[0].id : current));
      })
      .catch((error: unknown) => {
        if (!cancelled) setLoadError(errorText(error, "Could not load conversations"));
      });
    return () => {
      cancelled = true;
    };
  }, [userId, initialDraft.id]);

  // Fetch a conversation's messages the first time it is opened.
  const pendingLoad =
    !activeSession.loaded && activeSession.conversationId ? activeSession.conversationId : null;
  useEffect(() => {
    if (!pendingLoad) return;
    let cancelled = false;
    fetchConversation(pendingLoad)
      .then((detail) => {
        if (cancelled) return;
        setSessions((prev) =>
          prev.map((session) =>
            session.conversationId === pendingLoad
              ? { ...session, messages: messagesFromServer(detail.messages), loaded: true }
              : session,
          ),
        );
      })
      .catch((error: unknown) => {
        if (!cancelled) setLoadError(errorText(error, "Could not load the conversation"));
      });
    return () => {
      cancelled = true;
    };
  }, [pendingLoad]);

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
        activeSession.conversationId,
        options,
        (conversationId) => updateSession(sessionId, (session) => ({ ...session, conversationId })),
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
        content: `Error: ${errorText(error, "chat request failed")}`,
      }));
    } finally {
      setStreaming(sessionId, false);
    }
  }

  function handleCreate() {
    // Reuse an untouched chat instead of piling up empty "New chat" entries.
    const empty = sessions.find((session) => session.loaded && session.messages.length === 0);
    if (empty) {
      setActiveId(empty.id);
      return;
    }
    const session = createDraftSession();
    setSessions((prev) => [...prev, session]);
    setActiveId(session.id);
  }

  async function handleDelete(id: string) {
    const session = sessions.find((item) => item.id === id);
    if (session?.conversationId) {
      try {
        await deleteConversation(session.conversationId);
      } catch (error) {
        setLoadError(errorText(error, "Could not delete the conversation"));
        return;
      }
    }
    const remaining = sessions.filter((item) => item.id !== id);
    if (remaining.length === 0) {
      const draft = createDraftSession();
      setSessions([draft]);
      setActiveId(draft.id);
      return;
    }
    setSessions(remaining);
    if (id === activeId) {
      const next = remaining.reduce((latest, item) => (item.updatedAt > latest.updatedAt ? item : latest));
      setActiveId(next.id);
    }
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
        isLoading={!activeSession.loaded}
        error={loadError}
        onSend={handleSend}
      />
    </section>
  );
}
