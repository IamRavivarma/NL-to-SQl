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
