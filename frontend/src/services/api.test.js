import { afterEach, describe, expect, it, vi } from "vitest";
import { createSseParser, statsPath, streamQuery } from "./api";

describe("statsPath", () => {
  it("sends the browser's time-zone offset so days are counted in local time", () => {
    expect(statsPath(-330)).toBe("/api/stats?tz_offset_minutes=-330");
    expect(statsPath(0)).toBe("/api/stats?tz_offset_minutes=0");
  });
});

function collect() {
  const events = [];
  const feed = createSseParser((event, data) => events.push([event, data]));
  return { events, feed };
}

describe("createSseParser", () => {
  it("parses complete events", () => {
    const { events, feed } = collect();
    feed('event: meta\ndata: {"sources":[]}\n\nevent: token\ndata: {"text":"Hi"}\n\n');
    expect(events).toEqual([
      ["meta", { sources: [] }],
      ["token", { text: "Hi" }],
    ]);
  });

  it("joins an event split across reads", () => {
    const { events, feed } = collect();
    feed("event: tok");
    feed('en\ndata: {"text":" wor');
    expect(events).toEqual([]);
    feed('ld"}\n\n');
    expect(events).toEqual([["token", { text: " world" }]]);
  });

  it("handles CRLF line endings", () => {
    const { events, feed } = collect();
    feed('event: done\r\ndata: {"metrics":null}\r\n\r\n');
    expect(events).toEqual([["done", { metrics: null }]]);
  });

  it("handles a CRLF pair split across reads", () => {
    const { events, feed } = collect();
    feed('event: token\r\ndata: {"text":"a"}\r\n\r');
    feed("\n");
    feed('event: token\r\ndata: {"text":"b"}\r\n\r\n');
    expect(events).toEqual([
      ["token", { text: "a" }],
      ["token", { text: "b" }],
    ]);
  });

  it("handles lone CR line endings", () => {
    const { events, feed } = collect();
    feed('event: token\rdata: {"text":"a"}\r\r');
    feed('event: done\rdata: {"metrics":null}\r\r');
    expect(events).toEqual([["token", { text: "a" }]]); // a final CR could still be half of a CRLF
    feed.end();
    expect(events).toEqual([
      ["token", { text: "a" }],
      ["done", { metrics: null }],
    ]);
  });

  it("ignores a trailing incomplete event", () => {
    const { events, feed } = collect();
    feed('event: token\ndata: {"text":"a"}\n\nevent: token\ndata: {"te');
    expect(events).toEqual([["token", { text: "a" }]]);
  });
});

describe("streamQuery", () => {
  afterEach(() => vi.unstubAllGlobals());

  async function sentBody(args) {
    const fetch = vi.fn(async () => new Response("event: done\ndata: {}\n\n"));
    vi.stubGlobal("fetch", fetch);
    await streamQuery({ question: "Leave?", onEvent: () => {}, ...args });
    return JSON.parse(fetch.mock.calls[0][1].body);
  }

  it("sends the selected file's id", async () => {
    expect((await sentBody({ documentId: "a" })).document_id).toBe("a");
  });

  it("sends null when no file is selected", async () => {
    expect((await sentBody({})).document_id).toBeNull();
  });
});
