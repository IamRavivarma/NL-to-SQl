import { LoaderCircle, Upload } from "lucide-react";
import { useState } from "react";
import { uploadDocument } from "../services/api";

export default function FileUpload({ onUploaded }) {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const [dragging, setDragging] = useState(false);

  async function upload(file) {
    if (!file || status) return;
    setError(null);
    setStatus(`Reading ${file.name}…`);
    try {
      await uploadDocument(file);
      onUploaded();
    } catch (err) {
      setError(err.message);
    } finally {
      setStatus(null);
    }
  }

  function handleDrop(event) {
    event.preventDefault();
    setDragging(false);
    upload(event.dataTransfer.files[0]);
  }

  return (
    <div>
      <label
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={`flex cursor-pointer flex-col items-center gap-1.5 rounded-xl border border-dashed px-4 py-5 text-center transition-colors focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-accent ${
          dragging ? "border-accent bg-accent-soft" : "border-line bg-canvas hover:border-accent/50 hover:bg-accent-soft/60"
        }`}
      >
        {status ? (
          <LoaderCircle className="size-5 animate-spin text-accent" aria-hidden="true" />
        ) : (
          <Upload className="size-5 text-accent" aria-hidden="true" />
        )}
        <span className="text-sm font-medium text-ink">{status ?? "Drop a file or browse"}</span>
        <span className="text-xs text-muted">PDF, TXT, DOCX, CSV or XLSX up to 20 MB</span>
        <input
          type="file"
          accept=".pdf,.txt,.docx,.csv,.xlsx"
          className="sr-only"
          disabled={!!status}
          onChange={(event) => {
            upload(event.target.files[0]);
            event.target.value = "";
          }}
        />
      </label>
      {error && (
        <p role="alert" className="mt-2 text-xs leading-relaxed text-red-600">
          {error}
        </p>
      )}
    </div>
  );
}
