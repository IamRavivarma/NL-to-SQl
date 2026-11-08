import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import ChatView from "./ChatView";

const render = (selectedDocument) =>
  renderToStaticMarkup(
    <ChatView
      conversationId={null}
      hasDocuments
      selectedDocument={selectedDocument}
      onClearSelection={() => {}}
      onConversationStarted={() => {}}
      onAnswerFinished={() => {}}
      onBusyChange={() => {}}
    />,
  );

describe("ChatView", () => {
  it("says which file questions will be answered from", () => {
    const html = render({ id: "a", filename: "handbook.pdf" });
    expect(html).toContain("Asking about");
    expect(html).toContain("handbook.pdf");
    expect(html).toContain('placeholder="Ask about handbook.pdf…"');
    expect(html).toContain('aria-label="Ask about all documents"');
  });

  it("asks about all documents when nothing is selected", () => {
    const html = render(null);
    expect(html).not.toContain("Asking about");
    expect(html).toContain('placeholder="Ask anything about your documents…"');
  });
});
