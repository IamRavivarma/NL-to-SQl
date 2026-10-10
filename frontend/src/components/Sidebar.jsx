import ConversationList from "./ConversationList";
import DocumentList from "./DocumentList";
import FileUpload from "./FileUpload";

export default function Sidebar({
  documents,
  conversations,
  activeConversationId,
  busy,
  onUploaded,
  onDeleteDocument,
  onSelectConversation,
  onDeleteConversation,
  onNewChat,
}) {
  return (
    <aside className="flex w-72 shrink-0 flex-col gap-5 overflow-y-auto border-r border-slate-200 bg-slate-50 p-4">
      <section className="space-y-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Documents</h2>
        <FileUpload onUploaded={onUploaded} />
        <DocumentList documents={documents} onDelete={onDeleteDocument} />
      </section>
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Conversations</h2>
          <button
            type="button"
            onClick={onNewChat}
            disabled={busy}
            className="rounded bg-indigo-600 px-2 py-1 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            New chat
          </button>
        </div>
        <ConversationList
          conversations={conversations}
          activeId={activeConversationId}
          disabled={busy}
          onSelect={onSelectConversation}
          onDelete={onDeleteConversation}
        />
      </section>
    </aside>
  );
}
