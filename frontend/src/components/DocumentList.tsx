import { useState } from "react";
import type { DocumentOut } from "../api/client";
import { deleteDocument } from "../api/client";

interface DocumentListProps {
  documents: DocumentOut[];
  onDeleted: () => void;
}

const STATUS_LABELS: Record<string, string> = {
  pending: "Pending",
  processing: "Processing",
  ready: "Ready",
  failed: "Failed",
};

export default function DocumentList({ documents, onDeleted }: DocumentListProps) {
  const [error, setError] = useState<string | null>(null);

  async function handleDelete(documentId: string) {
    if (!confirm("Delete this document? This cannot be undone.")) return;
    setError(null);
    try {
      await deleteDocument(documentId);
      onDeleted();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  if (documents.length === 0) {
    return <p className="empty-hint">No documents visible to this role — upload one above.</p>;
  }

  return (
    <div className="table-scroll">
      {error && <p className="error">{error}</p>}
      <table className="document-list">
        <thead>
          <tr>
            <th>Filename</th>
            <th>Classification</th>
            <th>Tags</th>
            <th>Created by</th>
            <th>Size</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => (
            <tr key={doc.id}>
              <td title={doc.mime_type}>{doc.filename}</td>
              <td>
                <span className={`classification-badge ${doc.classification}`}>
                  {doc.classification}
                </span>
              </td>
              <td>{doc.tags.join(", ")}</td>
              <td>{doc.created_by_username ?? "—"}</td>
              <td>{(doc.size_bytes / 1024).toFixed(1)} KB</td>
              <td>
                <span className={`status-badge ${doc.status}`}>
                  {STATUS_LABELS[doc.status] ?? doc.status}
                </span>
              </td>
              <td>
                {doc.can_delete && (
                  <button onClick={() => void handleDelete(doc.id)}>Delete</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
