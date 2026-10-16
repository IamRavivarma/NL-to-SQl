import { useCallback, useEffect, useState } from "react";
import ChatView from "./components/ChatView";
import Dashboard from "./components/Dashboard";
import Sidebar from "./components/Sidebar";
import { tabFromHash } from "./lib/format";
import { checkHealth, deleteConversation, deleteDocument, listConversations, listDocuments } from "./services/api";

const TABS = [
  { id: "chat", label: "Chat" },
  { id: "dashboard", label: "Dashboard" },
];

function ConnectionStatus({ online }) {
  if (online === null) return null;
  return (
    <span className="flex items-center gap-2 text-xs text-muted" role="status">
      <span className={`size-2 rounded-full ${online ? "bg-emerald-500" : "bg-red-500"}`} aria-hidden="true" />
      {online ? "Connected" : "Backend offline"}
    </span>
  );
}

export default function App() {
  const [tab, setTab] = useState(() => tabFromHash(window.location.hash));
  const [documents, setDocuments] = useState([]);
  const [conversations, setConversations] = useState([]);
  const [activeConversationId, setActiveConversationId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [online, setOnline] = useState(null);

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

  useEffect(() => {
    const poll = async () => setOnline(await checkHealth());
    poll();
    const timer = setInterval(poll, 15000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const onHashChange = () => setTab(tabFromHash(window.location.hash));
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  function showTab(id) {
    setTab(id);
    window.history.replaceState(null, "", id === "chat" ? window.location.pathname : `#${id}`);
  }

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
          showTab("chat");
        }}
        onDeleteConversation={handleDeleteConversation}
        onNewChat={() => {
          setActiveConversationId(null);
          showTab("chat");
        }}
      />
      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between px-6 pt-4">
          <nav className="flex gap-1 rounded-xl bg-surface p-1 ring-1 ring-line" aria-label="Views">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => showTab(t.id)}
                aria-current={tab === t.id ? "page" : undefined}
                className={`rounded-lg px-4 py-1.5 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-accent ${
                  tab === t.id ? "bg-accent text-white" : "text-muted hover:text-ink"
                }`}
              >
                {t.label}
              </button>
            ))}
          </nav>
          <ConnectionStatus online={online} />
        </header>
        {error && (
          <p role="alert" className="mx-6 mt-3 rounded-lg bg-red-50 px-4 py-2 text-sm text-red-700">
            {error}
          </p>
        )}
        <div className="min-h-0 flex-1">
          {tab === "chat" ? (
            <ChatView
              conversationId={activeConversationId}
              hasDocuments={documents.length > 0}
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
