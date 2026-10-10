import { describe, expect, it } from "vitest";
import { createSseParser } from "./api";

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

  it("ignores a trailing incomplete event", () => {
    const { events, feed } = collect();
    feed('event: token\ndata: {"text":"a"}\n\nevent: token\ndata: {"te');
    expect(events).toEqual([["token", { text: "a" }]]);
  });
});
