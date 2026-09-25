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

function cacheNote(retrieval: RetrievalSummary): string | null {
  if (retrieval.cache_status !== "hit") return null;
  const similarity =
    retrieval.cache_similarity !== null ? ` (similarity ${retrieval.cache_similarity.toFixed(3)})` : "";
  return `Answered from the semantic cache${similarity}`;
}

function memoryNote(retrieval: RetrievalSummary): string | null {
  const used = retrieval.history_turns_used;
  if (!used) return null;
  const turns = `${used} previous turn${used === 1 ? "" : "s"}`;
  return retrieval.standalone_question
    ? `Used ${turns} · searched as: "${retrieval.standalone_question}"`
    : `Used ${turns}`;
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const retrieval = message.role === "assistant" ? message.retrieval : null;
  const note = retrieval ? rerankNote(retrieval) : null;
  const cached = retrieval ? cacheNote(retrieval) : null;
  const memory = retrieval ? memoryNote(retrieval) : null;
  return (
    <div className={`message-bubble ${message.role}`}>
      <div className="message-content">{message.content}</div>
      {cached && <p className="retrieval-note cache">{cached}</p>}
      {memory && <p className="retrieval-note memory">{memory}</p>}
      {note && <p className={`retrieval-note ${retrieval?.rerank_status ?? ""}`}>{note}</p>}
      {message.role === "assistant" && message.citations && (
        <CitationList citations={message.citations} />
      )}
    </div>
  );
}
