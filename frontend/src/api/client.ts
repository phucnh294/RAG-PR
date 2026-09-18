const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface DocumentOut {
  id: string;
  filename: string;
  content_hash: string;
  mime_type: string;
  size_bytes: number;
  status: string;
  created_at: string;
}

export interface UploadResponse {
  document: DocumentOut;
  already_exists: boolean;
}

export async function fetchDocuments(): Promise<DocumentOut[]> {
  const response = await fetch(`${API_BASE}/documents`);
  if (!response.ok) {
    throw new Error(`Failed to fetch documents: ${response.status}`);
  }
  return response.json();
}

export async function uploadDocument(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${API_BASE}/documents`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(detail.detail ?? `Upload failed: ${response.status}`);
  }
  return response.json();
}

export async function deleteDocument(documentId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/documents/${documentId}`, { method: "DELETE" });
  if (!response.ok) {
    throw new Error(`Failed to delete document: ${response.status}`);
  }
}

export { API_BASE };
