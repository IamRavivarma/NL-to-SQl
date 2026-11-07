import { ArrowUp, LoaderCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { getConversation, streamQuery } from "../services/api";
import EmptyState from "./EmptyState";
import MessageBubble from "./MessageBubble";

const STREAMING_ID = "streaming";

export default function ChatView({
  conversationId,
  hasDocuments,
  onConversationStarted,
  onAnswerFinished,
  onBusyChange,
}) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState(null);
  // Id of the conversation whose messages are already on screen (e.g. one we just started by streaming).
  const shownIdRef = useRef(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    if (conversationId === shownIdRef.current) return;
    shownIdRef.current = conversationId;
    setLoadError(null);
    if (conversationId === null) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    getConversation(conversationId)
      .then((conversation) => !cancelled && setMessages(conversation.messages))
      .catch((err) => !cancelled && setLoadError(err.message));
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function setBusyState(value) {
    setBusy(value);
    onBusyChange(value);
  }

  function updateStreaming(patch) {
    setMessages((prev) =>
      prev.map((m) => (m.id === STREAMING_ID ? { ...m, ...(typeof patch === "function" ? patch(m) : patch) } : m)),
    );
  }

  function adoptConversation(id) {
    if (id && id !== shownIdRef.current) {
      shownIdRef.current = id;
      onConversationStarted(id);
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    ask(input.trim());
  }

  async function ask(question) {
    if (!question || busy) return;

    setInput("");
    setBusyState(true);
    setMessages((prev) => [
      ...prev,
      { id: `user-${Date.now()}`, role: "user", content: question },
      { id: STREAMING_ID, role: "assistant", content: "", sources: [], queries: [], metrics: null, status: "streaming" },
    ]);

    try {
      await streamQuery({
        question,
        conversationId,
        onEvent: (name, data) => {
          if (name === "meta") {
            adoptConversation(data.conversation_id);
            updateStreaming({ sources: data.sources, queries: data.queries ?? [] });
          } else if (name === "token") {
            updateStreaming((m) => ({ content: m.content + data.text }));
          } else if (name === "done") {
            updateStreaming({
              id: data.message_id,
              status: "complete",
              metrics: data.metrics,
              sources: data.sources,
              queries: data.queries ?? [],
            });
          } else if (name === "error") {
            adoptConversation(data.conversation_id);
            updateStreaming({ id: `error-${Date.now()}`, status: "error", error: data.message });
          }
        },
      });
      // Stream ended without done/error (connection dropped). No-op if the answer already finished.
      updateStreaming({ id: `error-${Date.now()}`, status: "error", error: "The answer was interrupted." });
    } catch (err) {
      updateStreaming({ id: `error-${Date.now()}`, status: "error", error: err.message });
    } finally {
      setBusyState(false);
      onAnswerFinished();
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl space-y-6 px-6 pb-8 pt-8">
          {loadError && (
            <p role="alert" className="text-sm text-red-600">
              {loadError}
            </p>
          )}
          {messages.length === 0 && !loadError && <EmptyState hasDocuments={hasDocuments} onPick={ask} />}
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}
          <div ref={bottomRef} />
        </div>
      </div>
      <div className="px-6 pb-6">
        <form
          onSubmit={handleSubmit}
          className="mx-auto flex max-w-3xl items-center gap-2 rounded-2xl border border-line bg-surface p-2 pl-4 shadow-[0_8px_30px_-12px_rgba(23,26,44,0.25)] focus-within:border-accent/50"
        >
          <label htmlFor="question" className="sr-only">
            Your question
          </label>
          <input
            id="question"
            className="min-w-0 flex-1 bg-transparent py-2 text-[15px] placeholder:text-muted focus:outline-none"
            placeholder={hasDocuments ? "Ask anything about your documents…" : "Upload a document to start asking questions"}
            value={input}
            maxLength={2000}
            onChange={(e) => setInput(e.target.value)}
            disabled={busy}
            autoComplete="off"
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            aria-label={busy ? "Answering" : "Send question"}
            className="grid size-10 shrink-0 place-items-center rounded-xl bg-accent text-white transition-colors hover:bg-accent-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:bg-line disabled:text-muted"
          >
            {busy ? (
              <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
            ) : (
              <ArrowUp className="size-5" aria-hidden="true" />
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
