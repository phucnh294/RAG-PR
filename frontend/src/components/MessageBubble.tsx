import type {
  Citation,
  EvidenceSummary,
  GuardrailVerdict,
  RetrievalSummary,
} from "../api/streaming";
import CitationList from "./CitationList";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  guardrails?: GuardrailVerdict[];
  evidence?: EvidenceSummary;
  retrieval?: RetrievalSummary | null;
}

interface MessageBubbleProps {
  message: ChatMessage;
}

function rerankNote(retrieval: RetrievalSummary): string | null {
  switch (retrieval.rerank_status) {
    case "applied":
      return `Reranked by cross-encoder${
        retrieval.rerank_duration_ms !== null ? ` in ${Math.round(retrieval.rerank_duration_ms)} ms` : ""
      }`;
    case "failed":
      return `Rerank failed — showing ${retrieval.search_mode} search order`;
    case "skipped":
      return "Rerank on — no candidates to rerank";
    default:
      return null;
  }
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const note = message.retrieval ? rerankNote(message.retrieval) : null;
  return (
    <div className={`message-bubble ${message.role}`}>
      <div className="message-content">{message.content}</div>
      {message.role === "assistant" && note && (
        <p className={`retrieval-note ${message.retrieval?.rerank_status ?? ""}`}>{note}</p>
      )}
      {message.role === "assistant" && message.citations && (
        <CitationList citations={message.citations} />
      )}
    </div>
  );
}
