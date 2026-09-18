import { useCallback, useEffect, useState } from "react";
import { fetchDocuments, type DocumentOut } from "../api/client";
import DocumentUpload from "../components/DocumentUpload";
import DocumentList from "../components/DocumentList";

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<DocumentOut[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    fetchDocuments()
      .then(setDocuments)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load documents"));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <section className="page">
      <h2>Documents</h2>
      <DocumentUpload onUploaded={refresh} />
      {error && <p className="error">{error}</p>}
      <DocumentList documents={documents} onDeleted={refresh} />
    </section>
  );
}
