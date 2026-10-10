import { useState } from "react";
import { uploadDocument } from "../services/api";

export default function FileUpload({ onUploaded }) {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);

  async function handleChange(event) {
    const file = event.target.files[0];
    event.target.value = "";
    if (!file) return;
    setError(null);
    setStatus(`Processing ${file.name}…`);
    try {
      await uploadDocument(file);
      onUploaded();
    } catch (err) {
      setError(err.message);
    } finally {
      setStatus(null);
    }
  }

  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white p-3">
      <label className="block cursor-pointer text-sm font-medium text-indigo-600 hover:text-indigo-700">
        + Upload PDF, TXT or DOCX
        <input type="file" accept=".pdf,.txt,.docx" className="hidden" onChange={handleChange} disabled={!!status} />
      </label>
      <p className="mt-1 text-xs text-slate-500">Max 20 MB</p>
      {status && <p className="mt-2 text-xs text-slate-600">{status}</p>}
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
    </div>
  );
}
