import { MessageSquare, Trash2 } from "lucide-react";

export default function ConversationList({ conversations, activeId, disabled, onSelect, onDelete }) {
  if (conversations.length === 0) {
    return <p className="px-1 text-xs text-muted">Your questions will be saved here.</p>;
  }
  return (
    <ul className="space-y-0.5">
      {conversations.map((c) => {
        const active = c.id === activeId;
        return (
          <li
            key={c.id}
            className={`group flex items-center rounded-lg ${active ? "bg-accent-soft text-accent-strong" : "text-ink hover:bg-canvas"}`}
          >
            <button
              type="button"
              disabled={disabled}
              onClick={() => onSelect(c.id)}
              aria-current={active ? "true" : undefined}
              className="flex min-w-0 flex-1 items-center gap-2.5 px-2 py-2 text-left text-sm disabled:cursor-not-allowed"
              title={c.title}
            >
              <MessageSquare className={`size-4 shrink-0 ${active ? "text-accent" : "text-muted"}`} aria-hidden="true" />
              <span className="truncate">{c.title}</span>
            </button>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onDelete(c.id)}
              className="mr-1 rounded-md p-1.5 text-muted opacity-0 transition hover:bg-red-50 hover:text-red-600 focus-visible:opacity-100 group-hover:opacity-100"
              aria-label={`Delete conversation ${c.title}`}
            >
              <Trash2 className="size-4" aria-hidden="true" />
            </button>
          </li>
        );
      })}
    </ul>
  );
}
