import type { ChatSession } from "../chat/sessions";

interface ChatSessionListProps {
  sessions: ChatSession[];
  activeId: string;
  streamingIds: ReadonlySet<string>;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
}

export default function ChatSessionList({
  sessions,
  activeId,
  streamingIds,
  onSelect,
  onCreate,
  onDelete,
}: ChatSessionListProps) {
  const ordered = [...sessions].sort((a, b) => b.updatedAt - a.updatedAt);

  return (
    <aside className="chat-sessions">
      <button className="chat-sessions-new" onClick={onCreate}>
        + New chat
      </button>
      <ul>
        {ordered.map((session) => {
          const streaming = streamingIds.has(session.id);
          return (
            <li key={session.id} className={session.id === activeId ? "active" : ""}>
              <button
                className="chat-session-title"
                onClick={() => onSelect(session.id)}
                title={session.title}
              >
                {streaming && <span className="chat-session-dot" aria-label="answering" />}
                {session.title}
              </button>
              <button
                className="chat-session-delete"
                onClick={() => onDelete(session.id)}
                disabled={streaming}
                aria-label={`Delete chat "${session.title}"`}
                title="Delete chat"
              >
                ×
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
