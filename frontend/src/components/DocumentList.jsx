export default function DocumentList({ documents, onDelete }) {
  if (documents.length === 0) {
    return <p className="text-xs text-slate-500">No documents yet.</p>;
  }
  return (
    <ul className="space-y-1">
      {documents.map((doc) => (
        <li key={doc.id} className="group flex items-center justify-between rounded px-2 py-1 text-sm hover:bg-slate-100">
          <span className="truncate" title={doc.filename}>
            {doc.filename}
            <span className="ml-1 text-xs text-slate-400">{doc.chunk_count} chunks</span>
          </span>
          <button
            type="button"
            onClick={() => onDelete(doc.id)}
            className="ml-2 text-xs text-slate-400 opacity-0 hover:text-red-600 group-hover:opacity-100"
            aria-label={`Delete ${doc.filename}`}
          >
            Delete
          </button>
        </li>
      ))}
    </ul>
  );
}
