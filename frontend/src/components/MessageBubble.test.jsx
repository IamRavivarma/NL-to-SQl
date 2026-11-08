import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import MessageBubble from "./MessageBubble";

function renderAnswer(content) {
  return renderToStaticMarkup(
    <MessageBubble message={{ id: "1", role: "assistant", content, sources: [], metrics: null, status: "complete" }} />,
  );
}

describe("MessageBubble", () => {
  it("renders Markdown tables as HTML tables", () => {
    const html = renderAnswer("| Plan | Price |\n|---|---|\n| Basic | $5 |");
    expect(html).toContain("<table>");
    expect(html).toContain("<td>Basic</td>");
  });

  it("renders bold text", () => {
    expect(renderAnswer("Refunds take **ten days**.")).toContain("<strong>ten days</strong>");
  });
});

describe("MessageBubble question", () => {
  it("shows the file a question was asked about", () => {
    const html = renderToStaticMarkup(
      <MessageBubble message={{ id: "q", role: "user", content: "Leave?", document_filename: "handbook.pdf" }} />,
    );
    expect(html).toContain("handbook.pdf");
  });

  it("shows no file tag for questions about all documents", () => {
    const html = renderToStaticMarkup(<MessageBubble message={{ id: "q", role: "user", content: "Leave?" }} />);
    expect(html).not.toContain("<svg");
  });
});
