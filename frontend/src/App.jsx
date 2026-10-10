import { useCallback, useEffect, useState } from "react";
import ChatView from "./components/ChatView";
import Dashboard from "./components/Dashboard";
import Sidebar from "./components/Sidebar";
import { deleteConversation, deleteDocument, listConversations, listDocuments } from "./services/api";

const TABS = [
  { id: "chat", label: "Chat" },
  { id: "dashboard", label: "Dashboard" },
];

export default function App() {
  const [tab, setTab] = useState("chat");
  const [documents, setDocuments] = useState([]);
  const [conversations, setConversations] = useState([]);
  const [activeConversationId, setActiveConversationId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const run = useCallback(async (action) => {
    try {
      setError(null);
      await action();
    } catch (err) {
      setError(err.message);
    }
  }, []);

  const refreshDocuments = useCallback(() => run(async () => setDocuments(await listDocuments())), [run]);
  const refreshConversations = useCallback(
    () => run(async () => setConversations(await listConversations())),
    [run],
  );

  useEffect(() => {
    refreshDocuments();
    refreshConversations();
  }, [refreshDocuments, refreshConversations]);

  function handleDeleteDocument(id) {
    run(async () => {
      await deleteDocument(id);
      setDocuments(await listDocuments());
    });
  }

  function handleDeleteConversation(id) {
    run(async () => {
      await deleteConversation(id);
      if (id === activeConversationId) setActiveConversationId(null);
      setConversations(await listConversations());
    });
  }

  return (
    <div className="flex h-screen">
      <Sidebar
        documents={documents}
        conversations={conversations}
        activeConversationId={activeConversationId}
        busy={busy}
        onUploaded={refreshDocuments}
        onDeleteDocument={handleDeleteDocument}
        onSelectConversation={(id) => {
          setActiveConversationId(id);
          setTab("chat");
        }}
        onDeleteConversation={handleDeleteConversation}
        onNewChat={() => {
          setActiveConversationId(null);
          setTab("chat");
        }}
      />
      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-1 border-b border-slate-200 bg-white px-4">
          <h1 className="mr-6 py-3 font-semibold">⚡ RAG Data Assistant</h1>
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`border-b-2 px-3 py-3 text-sm font-medium ${
                tab === t.id ? "border-indigo-600 text-indigo-600" : "border-transparent text-slate-500 hover:text-slate-700"
              }`}
            >
              {t.label}
            </button>
          ))}
        </header>
        {error && <p className="bg-red-50 px-4 py-2 text-sm text-red-700">{error}</p>}
        <div className="min-h-0 flex-1">
          {tab === "chat" ? (
            <ChatView
              conversationId={activeConversationId}
              onConversationStarted={setActiveConversationId}
              onAnswerFinished={refreshConversations}
              onBusyChange={setBusy}
            />
          ) : (
            <Dashboard />
          )}
        </div>
      </main>
    </div>
  );
}
