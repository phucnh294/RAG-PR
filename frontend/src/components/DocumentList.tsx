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
  async function handleDelete(documentId: string) {
    if (!confirm("Delete this document? This cannot be undone.")) return;
    await deleteDocument(documentId);
    onDeleted();
  }

  if (documents.length === 0) {
    return <p className="empty-hint">No documents yet — upload one above.</p>;
  }

  return (
    <table className="document-list">
      <thead>
        <tr>
          <th>Filename</th>
          <th>Type</th>
          <th>Size</th>
          <th>Status</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {documents.map((doc) => (
          <tr key={doc.id}>
            <td>{doc.filename}</td>
            <td>{doc.mime_type}</td>
            <td>{(doc.size_bytes / 1024).toFixed(1)} KB</td>
            <td>
              <span className={`status-badge ${doc.status}`}>
                {STATUS_LABELS[doc.status] ?? doc.status}
              </span>
            </td>
            <td>
              <button onClick={() => void handleDelete(doc.id)}>Delete</button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
