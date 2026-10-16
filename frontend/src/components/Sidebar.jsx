import { Plus, Zap } from "lucide-react";
import ConversationList from "./ConversationList";
import DocumentList from "./DocumentList";
import FileUpload from "./FileUpload";

function SectionTitle({ children }) {
  return <h2 className="px-1 text-[13px] font-semibold text-muted">{children}</h2>;
}

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
    <aside className="flex w-72 shrink-0 flex-col border-r border-line bg-surface">
      <div className="flex items-center gap-2.5 px-5 pb-4 pt-5">
        <span className="grid size-8 place-items-center rounded-lg bg-accent text-white">
          <Zap className="size-4" fill="currentColor" aria-hidden="true" />
        </span>
        <span className="text-[15px] font-semibold tracking-tight">Document Assistant</span>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto px-4 pb-4">
        <section className="space-y-3">
          <SectionTitle>Documents</SectionTitle>
          <FileUpload onUploaded={onUploaded} />
          <DocumentList documents={documents} onDelete={onDeleteDocument} />
        </section>

        <section className="space-y-2">
          <div className="flex items-center justify-between">
            <SectionTitle>Conversations</SectionTitle>
            <button
              type="button"
              onClick={onNewChat}
              disabled={busy}
              className="flex items-center gap-1 rounded-md px-2 py-1 text-[13px] font-medium text-accent hover:bg-accent-soft disabled:opacity-50"
            >
              <Plus className="size-3.5" aria-hidden="true" />
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
      </div>
    </aside>
  );
}
