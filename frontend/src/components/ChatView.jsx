import { useEffect, useRef, useState } from "react";
import { getConversation, streamQuery } from "../services/api";
import MessageBubble from "./MessageBubble";

const STREAMING_ID = "streaming";

export default function ChatView({ conversationId, onConversationStarted, onAnswerFinished, onBusyChange }) {
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

  async function handleSubmit(event) {
    event.preventDefault();
    const question = input.trim();
    if (!question || busy) return;

    setInput("");
    setBusyState(true);
    setMessages((prev) => [
      ...prev,
      { id: `user-${Date.now()}`, role: "user", content: question },
      { id: STREAMING_ID, role: "assistant", content: "", sources: [], metrics: null, status: "streaming" },
    ]);

    try {
      await streamQuery({
        question,
        conversationId,
        onEvent: (name, data) => {
          if (name === "meta") {
            adoptConversation(data.conversation_id);
            updateStreaming({ sources: data.sources });
          } else if (name === "token") {
            updateStreaming((m) => ({ content: m.content + data.text }));
          } else if (name === "done") {
            updateStreaming({ id: data.message_id, status: "complete", metrics: data.metrics, sources: data.sources });
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
      <div className="flex-1 space-y-4 overflow-y-auto p-6">
        {loadError && <p className="text-sm text-red-600">{loadError}</p>}
        {messages.length === 0 && !loadError && (
          <div className="mt-20 text-center text-slate-500">
            <p className="text-lg font-medium text-slate-700">Ask anything about your documents</p>
            <p className="mt-1 text-sm">Upload a PDF, TXT or DOCX on the left, then ask a question.</p>
          </div>
        )}
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        <div ref={bottomRef} />
      </div>
      <form onSubmit={handleSubmit} className="flex gap-2 border-t border-slate-200 bg-white p-4">
        <input
          className="flex-1 rounded-lg border border-slate-300 px-3 py-2 focus:border-indigo-500 focus:outline-none"
          placeholder="Ask a question about your documents…"
          value={input}
          maxLength={2000}
          onChange={(e) => setInput(e.target.value)}
          disabled={busy}
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {busy ? "Answering…" : "Send"}
        </button>
      </form>
    </div>
  );
}
