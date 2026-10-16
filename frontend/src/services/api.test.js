import { describe, expect, it } from "vitest";
import { createSseParser, statsPath } from "./api";

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
