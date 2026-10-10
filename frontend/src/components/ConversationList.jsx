export default function ConversationList({ conversations, activeId, disabled, onSelect, onDelete }) {
  if (conversations.length === 0) {
    return <p className="text-xs text-slate-500">No conversations yet.</p>;
  }
  return (
    <ul className="space-y-1">
      {conversations.map((c) => (
        <li
          key={c.id}
          className={`group flex items-center justify-between rounded px-2 py-1 text-sm ${
            c.id === activeId ? "bg-indigo-50 text-indigo-700" : "hover:bg-slate-100"
          }`}
        >
          <button
            type="button"
            disabled={disabled}
            onClick={() => onSelect(c.id)}
            className="flex-1 truncate text-left disabled:cursor-not-allowed"
            title={c.title}
          >
            {c.title}
          </button>
          <button
            type="button"
            disabled={disabled}
            onClick={() => onDelete(c.id)}
            className="ml-2 text-xs text-slate-400 opacity-0 hover:text-red-600 group-hover:opacity-100"
            aria-label={`Delete conversation ${c.title}`}
          >
            Delete
          </button>
        </li>
      ))}
    </ul>
  );
}
