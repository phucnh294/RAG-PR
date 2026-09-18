import type { Citation } from "../api/streaming";

interface CitationListProps {
  citations: Citation[];
}

export default function CitationList({ citations }: CitationListProps) {
  if (citations.length === 0) return null;

  return (
    <details className="citation-list">
      <summary>{citations.length} source{citations.length > 1 ? "s" : ""}</summary>
      <ul>
        {citations.map((citation, index) => (
          <li key={`${citation.document_id}-${index}`}>
            <strong>{citation.filename}</strong>{" "}
            <span className="score">({Math.round(citation.similarity_score * 100)}%)</span>
            <p>{citation.excerpt}</p>
          </li>
        ))}
      </ul>
    </details>
  );
}
