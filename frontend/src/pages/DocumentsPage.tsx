import { useCallback, useEffect, useState } from "react";
import { fetchDocuments, type DocumentOut } from "../api/client";
import DocumentUpload from "../components/DocumentUpload";
import DocumentList from "../components/DocumentList";

interface DocumentsPageProps {
  /** True while this tab is shown: the list re-syncs each time the tab is opened, keeping
   * what's on screen until the fresh list arrives. */
  active: boolean;
}

export default function DocumentsPage({ active }: DocumentsPageProps) {
  const [documents, setDocuments] = useState<DocumentOut[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    fetchDocuments()
      .then(setDocuments)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load documents"));
  }, []);

  useEffect(() => {
    if (active) refresh();
  }, [active, refresh]);

  return (
    <section className="page">
      <h2>Documents</h2>
      <DocumentUpload onUploaded={refresh} />
      {error && <p className="error">{error}</p>}
      <DocumentList documents={documents} onDeleted={refresh} />
    </section>
  );
}
