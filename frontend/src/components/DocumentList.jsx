import { FileText, Trash2 } from "lucide-react";
import { chunkLabel } from "../lib/format";

const TYPE_TINT = {
  pdf: "bg-rose-50 text-rose-600",
  docx: "bg-sky-50 text-sky-600",
  txt: "bg-slate-100 text-slate-600",
  csv: "bg-emerald-50 text-emerald-600",
  xlsx: "bg-emerald-50 text-emerald-600",
};

export default function DocumentList({ documents, onDelete }) {
  if (documents.length === 0) {
    return <p className="px-1 text-xs text-muted">Nothing uploaded yet.</p>;
  }
  return (
    <ul className="space-y-1">
      {documents.map((doc) => (
        <li key={doc.id} className="group flex items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-canvas">
          <span
            className={`grid size-8 shrink-0 place-items-center rounded-md ${TYPE_TINT[doc.file_type] ?? TYPE_TINT.txt}`}
            title={doc.file_type.toUpperCase()}
          >
            <FileText className="size-4" aria-hidden="true" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm text-ink" title={doc.filename}>
              {doc.filename}
            </span>
            <span className="tabular block text-xs text-muted">{chunkLabel(doc.chunk_count)}</span>
          </span>
          <button
            type="button"
            onClick={() => onDelete(doc.id)}
            className="rounded-md p-1.5 text-muted opacity-0 transition hover:bg-red-50 hover:text-red-600 focus-visible:opacity-100 group-hover:opacity-100"
            aria-label={`Delete ${doc.filename}`}
          >
            <Trash2 className="size-4" aria-hidden="true" />
          </button>
        </li>
      ))}
    </ul>
  );
}
