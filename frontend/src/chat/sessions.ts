// Chat sessions are the UI's view of the backend's conversations (GET /conversations):
// the server stores every question and answer and feeds recent turns back to the LLM
// as conversation memory. A session starts as a local draft (conversationId null) and
// gets its server id from the first /chat response; existing conversations load their
// messages lazily, the first time they are opened.

import type { ConversationMessageOut, ConversationOut } from "../api/client";
import type { ChatMessage } from "../components/MessageBubble";

export interface ChatSession {
  // Stable local key: stays the same when a draft receives its server conversation id,
  // so an answer streaming into a draft never loses its session.
  id: string;
  conversationId: string | null;
  title: string;
  updatedAt: number;
  messages: ChatMessage[];
  // Whether messages were fetched from the server (always true for drafts).
  loaded: boolean;
}

const TITLE_LENGTH = 60;
export const NEW_CHAT_TITLE = "New chat";

function newId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function createDraftSession(): ChatSession {
  return {
    id: newId(),
    conversationId: null,
    title: NEW_CHAT_TITLE,
    updatedAt: Date.now(),
    messages: [],
    loaded: true,
  };
}

export function sessionFromConversation(conversation: ConversationOut): ChatSession {
  return {
    id: conversation.id,
    conversationId: conversation.id,
    title: conversation.title,
    updatedAt: Date.parse(conversation.updated_at),
    messages: [],
    loaded: false,
  };
}

export function messagesFromServer(messages: ConversationMessageOut[]): ChatMessage[] {
  return messages.map((message) =>
    message.role === "user"
      ? { role: "user", content: message.content }
      : {
          role: "assistant",
          content: message.content,
          citations: message.payload?.citations,
          guardrails: message.payload?.guardrails,
          evidence: message.payload?.evidence,
          retrieval: message.payload?.retrieval ?? null,
        },
  );
}

// Mirrors the backend's title_from_question, so a draft shows the same title before
// the conversation list is next reloaded.
export function titleFromQuestion(question: string): string {
  const oneLine = question.replace(/\s+/g, " ").trim();
  return oneLine.length > TITLE_LENGTH ? `${oneLine.slice(0, TITLE_LENGTH - 1)}…` : oneLine;
}
