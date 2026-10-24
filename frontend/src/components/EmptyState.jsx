import { FileUp } from "lucide-react";

export const SUGGESTIONS = [
  "Summarize my documents in a few bullet points",
  "What are the most important rules or policies?",
  "List any deadlines, dates or numbers mentioned",
  "What should a new reader know first?",
];

function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export default function EmptyState({ hasDocuments, onPick }) {
  return (
    <div className="mx-auto mt-[12vh] max-w-xl px-2">
      <h2 className="text-[2.5rem] font-semibold leading-tight tracking-[-0.035em] text-ink">{greeting()}.</h2>
      {hasDocuments ? (
        <>
          <p className="mt-2 text-lg text-muted">What would you like to know about your documents?</p>
          <div className="mt-8 flex flex-wrap gap-2">
            {SUGGESTIONS.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                onClick={() => onPick(suggestion)}
                className="rounded-full border border-line bg-surface px-4 py-2 text-left text-sm text-ink transition-colors hover:border-accent/40 hover:bg-accent-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                {suggestion}
              </button>
            ))}
          </div>
        </>
      ) : (
        <div className="mt-6 flex items-start gap-3 rounded-xl border border-dashed border-line bg-surface p-4 text-muted">
          <FileUp className="mt-0.5 size-5 shrink-0 text-accent" aria-hidden="true" />
          <p className="text-sm leading-relaxed">
            Upload a PDF, Word, text, CSV or Excel file in the sidebar. Once it's processed, ask anything about it
            here and every answer will point to the page or sheet it came from.
          </p>
        </div>
      )}
    </div>
  );
}
