import { useEffect, useRef, useState } from "react";
import { fetchClassifications, uploadDocument, type ClassificationsOut } from "../api/client";

interface DocumentUploadProps {
  onUploaded: () => void;
}

export default function DocumentUpload({ onUploaded }: DocumentUploadProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [options, setOptions] = useState<ClassificationsOut | null>(null);
  const [classification, setClassification] = useState("");
  const [tags, setTags] = useState("");

  useEffect(() => {
    fetchClassifications()
      .then((loaded) => {
        setOptions(loaded);
        setClassification(loaded.default);
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Failed to load classifications"),
      );
  }, []);

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    setError(null);
    setNotice(null);
    try {
      const result = await uploadDocument(file, { classification, tags });
      if (result.already_exists) {
        setNotice(`"${file.name}" is already indexed as ${result.document.classification}.`);
      }
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
      <label>
        Classification
        <select
          value={classification}
          disabled={isUploading || !options}
          onChange={(event) => setClassification(event.target.value)}
        >
          {options?.allowed.map((name) => (
            <option key={name} value={name}>
              {name}
              {name === options.default ? " (default)" : ""}
            </option>
          ))}
        </select>
      </label>
      <label>
        Tags
        <input
          type="text"
          placeholder="comma, separated"
          value={tags}
          disabled={isUploading}
          onChange={(event) => setTags(event.target.value)}
        />
      </label>
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.txt,.md"
        disabled={isUploading || !options}
        onChange={handleFileChange}
      />
      {isUploading && <span>Uploading...</span>}
      {notice && <span className="notice">{notice}</span>}
      {error && <span className="error">{error}</span>}
    </div>
  );
}
