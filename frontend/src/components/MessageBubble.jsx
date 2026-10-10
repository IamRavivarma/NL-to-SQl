import Markdown from "react-markdown";

function SpeedBadge({ metrics }) {
  if (!metrics) return null;
  return (
    <span
      className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700"
      title={`Time to first token · output speed (${metrics.model})`}
    >
      ⚡ {(metrics.ttft_ms / 1000).toFixed(2)}s · {Math.round(metrics.tokens_per_sec)} tok/s
    </span>
  );
}

function Sources({ sources }) {
  if (!sources?.length) return null;
  return (
    <details className="mt-2 text-sm">
      <summary className="cursor-pointer text-xs font-medium text-slate-500">Sources ({sources.length})</summary>
      <ul className="mt-2 space-y-2">
        {sources.map((s) => (
          <li key={`${s.filename}-${s.page}`} className="rounded border border-slate-200 bg-slate-50 p-2">
            <p className="text-xs font-semibold text-slate-700">
              {s.filename} · p. {s.page}
            </p>
            <p className="mt-1 text-xs text-slate-600">{s.snippet}</p>
          </li>
        ))}
      </ul>
    </details>
  );
}

export default function MessageBubble({ message }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] rounded-2xl rounded-br-sm bg-indigo-600 px-4 py-2 text-white">{message.content}</div>
      </div>
    );
  }

  const waiting = message.status === "streaming" && !message.content;
  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-2xl rounded-bl-sm border border-slate-200 bg-white px-4 py-3 shadow-sm">
        {waiting ? (
          <p className="animate-pulse text-slate-400">Searching your documents…</p>
        ) : (
          <div className="prose prose-sm max-w-none [&_li]:ml-4 [&_ol]:list-decimal [&_p]:my-1 [&_ul]:list-disc">
            <Markdown>{message.content}</Markdown>
          </div>
        )}
        {message.status === "error" && (
          <p className="mt-2 text-sm text-red-600">{message.error ?? "Sorry, something went wrong while answering."}</p>
        )}
        <Sources sources={message.sources} />
        {message.metrics && (
          <div className="mt-2">
            <SpeedBadge metrics={message.metrics} />
          </div>
        )}
      </div>
    </div>
  );
}
