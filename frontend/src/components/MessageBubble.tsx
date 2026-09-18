import type { Citation } from "../api/streaming";
import CitationList from "./CitationList";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
}

interface MessageBubbleProps {
  message: ChatMessage;
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  return (
    <div className={`message-bubble ${message.role}`}>
      <div className="message-content">{message.content}</div>
      {message.role === "assistant" && message.citations && (
        <CitationList citations={message.citations} />
      )}
    </div>
  );
}
