import { useRef, useState } from "react";
import { uploadDocument } from "../api/client";

interface DocumentUploadProps {
  onUploaded: () => void;
}

export default function DocumentUpload({ onUploaded }: DocumentUploadProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    setError(null);
    try {
      await uploadDocument(file);
      onUploaded();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  return (
    <div className="document-upload">
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.txt,.md"
        disabled={isUploading}
        onChange={handleFileChange}
      />
      {isUploading && <span>Uploading...</span>}
      {error && <span className="error">{error}</span>}
    </div>
  );
}
