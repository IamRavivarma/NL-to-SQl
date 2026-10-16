import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import EmptyState, { SUGGESTIONS } from "./EmptyState";

describe("EmptyState", () => {
  it("offers each suggested question as a button", () => {
    const html = renderToStaticMarkup(<EmptyState hasDocuments onPick={() => {}} />);
    expect(SUGGESTIONS.length).toBeGreaterThanOrEqual(3);
    for (const suggestion of SUGGESTIONS) {
      expect(html).toContain(suggestion);
    }
    expect(html.match(/<button/g)).toHaveLength(SUGGESTIONS.length);
  });

  it("asks for an upload instead of suggesting questions when there are no documents", () => {
    const html = renderToStaticMarkup(<EmptyState hasDocuments={false} onPick={() => {}} />);
    expect(html).not.toContain("<button");
    expect(html).toContain("Upload a PDF, TXT or DOCX");
  });
});
