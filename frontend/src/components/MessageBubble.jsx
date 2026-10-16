import { FileText, Gauge, Sparkles, TriangleAlert, Zap } from "lucide-react";
import { useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { formatSeconds } from "../lib/format";

function Speed({ metrics }) {
  return (
    <div className="tabular flex items-center gap-3 text-xs text-muted" title={`Answered by ${metrics.model}`}>
      <span className="flex items-center gap-1" title="Time until the first word appeared">
        <Zap className="size-3.5 text-accent" aria-hidden="true" />
        {formatSeconds(metrics.ttft_ms)}
      </span>
      <span className="flex items-center gap-1" title="Output speed">
        <Gauge className="size-3.5 text-accent" aria-hidden="true" />
        {Math.round(metrics.tokens_per_sec)} tok/s
      </span>
    </div>
  );
}

function Sources({ sources }) {
  const [open, setOpen] = useState(null);
  if (!sources?.length) return null;
  const selected = sources.find((s) => `${s.filename}-${s.page}` === open);
  return (
    <div className="mt-3">
      <div className="flex flex-wrap gap-1.5">
        {sources.map((s) => {
          const key = `${s.filename}-${s.page}`;
          const active = key === open;
          return (
            <button
              key={key}
              type="button"
              onClick={() => setOpen(active ? null : key)}
              aria-expanded={active}
              className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors ${
                active ? "border-accent/40 bg-accent-soft text-accent-strong" : "border-line text-muted hover:text-ink"
              }`}
            >
              <FileText className="size-3.5" aria-hidden="true" />
              <span className="max-w-40 truncate">{s.filename}</span>
              <span className="tabular">p. {s.page}</span>
            </button>
          );
        })}
      </div>
      {selected && (
        <blockquote className="mt-2 border-l-2 border-accent/40 pl-3 text-sm leading-relaxed text-muted">
          {selected.snippet}
        </blockquote>
      )}
    </div>
  );
}

export default function MessageBubble({ message }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-md bg-accent px-4 py-2.5 leading-relaxed text-white">
          {message.content}
        </div>
      </div>
    );
  }

  const waiting = message.status === "streaming" && !message.content;
  return (
    <div className="flex gap-3">
      <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full bg-accent-soft text-accent">
        <Sparkles className="size-4" aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1 rounded-2xl rounded-tl-md border border-line bg-surface px-5 py-4">
        {waiting ? (
          <p className="flex items-center gap-2 text-muted">
            <span className="size-2 animate-pulse rounded-full bg-accent" aria-hidden="true" />
            Searching your documents…
          </p>
        ) : (
          <div className="prose prose-slate max-w-none prose-p:my-1.5 prose-p:leading-relaxed prose-li:my-0.5 prose-table:text-sm">
            <Markdown remarkPlugins={[remarkGfm]}>{message.content}</Markdown>
          </div>
        )}
        {message.status === "error" && (
          <p role="alert" className="mt-2 flex items-center gap-2 text-sm text-red-600">
            <TriangleAlert className="size-4 shrink-0" aria-hidden="true" />
            {message.error ?? "Sorry, something went wrong while answering."}
          </p>
        )}
        <Sources sources={message.sources} />
        {message.metrics && (
          <div className="mt-3 border-t border-line pt-2.5">
            <Speed metrics={message.metrics} />
          </div>
        )}
      </div>
    </div>
  );
}
