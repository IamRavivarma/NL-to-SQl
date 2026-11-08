import { Check, ChevronDown, Copy, Database, TriangleAlert } from "lucide-react";
import { useState } from "react";

const rowLabel = (n) => `${n} ${n === 1 ? "row" : "rows"}`;

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() =>
        navigator.clipboard?.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        })
      }
      className="absolute right-2 top-2 rounded-md p-1.5 text-slate-400 transition-colors hover:bg-white/10 hover:text-white"
      aria-label="Copy query"
    >
      {copied ? <Check className="size-3.5" aria-hidden="true" /> : <Copy className="size-3.5" aria-hidden="true" />}
    </button>
  );
}

function ResultTable({ run }) {
  return (
    <div className="max-h-72 overflow-auto rounded-lg border border-line">
      <table className="w-full border-collapse text-left text-xs">
        <thead className="sticky top-0 bg-canvas">
          <tr>
            {run.columns.map((column) => (
              <th key={column} className="whitespace-nowrap border-b border-line px-3 py-2 font-semibold text-ink">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="tabular">
          {run.rows.map((row, i) => (
            <tr key={i} className="odd:bg-surface even:bg-canvas/50">
              {row.map((value, j) => (
                <td key={j} className="max-w-80 border-b border-line/60 px-3 py-1.5 align-top text-ink">
                  {value === null ? <span className="text-muted">—</span> : String(value)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function QueryCard({ run }) {
  const [open, setOpen] = useState(true);
  const isSql = run.kind === "sql";
  const where = isSql
    ? [...new Set((run.tables ?? []).map((t) => t.filename))].join(", ")
    : `Atlas Vector Search · ${run.label ?? "all documents"}`;
  const partial = run.row_count > run.rows.length;

  return (
    <section className="rounded-xl border border-line bg-canvas/60">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
      >
        <Database className="size-4 shrink-0 text-accent" aria-hidden="true" />
        <span className="text-sm font-semibold text-ink">SQL query</span>
        {where && <span className="min-w-0 truncate text-xs text-muted">· {where}</span>}
        <span className="tabular ml-auto shrink-0 text-xs text-muted">
          {run.error ? "failed" : rowLabel(run.row_count)}
        </span>
        <ChevronDown
          className={`size-4 shrink-0 text-muted transition-transform ${open ? "rotate-180" : ""}`}
          aria-hidden="true"
        />
      </button>
      {open && (
        <div className="space-y-2 px-3 pb-3">
          <div className="relative">
            <pre className="overflow-x-auto rounded-lg bg-[#171A2C] p-3 pr-10 text-xs leading-relaxed text-slate-100">
              <code>{run.query}</code>
            </pre>
            <CopyButton text={run.query} />
          </div>
          {run.error ? (
            <p role="alert" className="flex items-start gap-2 text-xs text-red-600">
              <TriangleAlert className="mt-px size-3.5 shrink-0" aria-hidden="true" />
              <span>
                The query failed: {run.error}
                {isSql && " — searched the documents instead."}
              </span>
            </p>
          ) : run.columns.length > 0 ? (
            <>
              <ResultTable run={run} />
              {partial && (
                <p className="tabular text-xs text-muted">
                  Showing {run.rows.length} of {run.row_count}
                  {run.truncated ? "+" : ""} rows
                </p>
              )}
            </>
          ) : (
            <p className="text-xs text-muted">No rows returned.</p>
          )}
        </div>
      )}
    </section>
  );
}

export default function QueryPanel({ queries }) {
  if (!queries?.length) return null;
  return (
    <div className="mb-3 space-y-2">
      {queries.map((run, i) => (
        <QueryCard key={i} run={run} />
      ))}
    </div>
  );
}
