import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import DocumentList from "./DocumentList";

const DOCS = [
  { id: "a", filename: "handbook.pdf", file_type: "pdf", chunk_count: 3 },
  { id: "b", filename: "sales.xlsx", file_type: "xlsx", chunk_count: 2 },
];

const render = (selectedId) =>
  renderToStaticMarkup(<DocumentList documents={DOCS} selectedId={selectedId} onSelect={() => {}} onDelete={() => {}} />);

describe("DocumentList", () => {
  it("marks only the selected file as pressed and highlighted", () => {
    const html = render("b");
    expect(html.match(/aria-pressed="true"/g)).toHaveLength(1);
    expect(html.match(/aria-pressed="false"/g)).toHaveLength(1);
    const selected = html.slice(html.indexOf('aria-pressed="true"') - 400, html.indexOf("sales.xlsx"));
    expect(selected).toContain("bg-accent-soft");
  });

  it("has nothing selected by default", () => {
    expect(render(null)).not.toContain('aria-pressed="true"');
  });
});
