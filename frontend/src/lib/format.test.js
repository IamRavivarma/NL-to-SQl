import { describe, expect, it } from "vitest";
import { chunkLabel, formatSeconds, tabFromHash } from "./format";

describe("chunkLabel", () => {
  it("uses the singular for one chunk", () => {
    expect(chunkLabel(1)).toBe("1 chunk");
  });

  it("uses the plural otherwise", () => {
    expect(chunkLabel(0)).toBe("0 chunks");
    expect(chunkLabel(12)).toBe("12 chunks");
  });
});

describe("formatSeconds", () => {
  it("shows milliseconds as seconds with two decimals", () => {
    expect(formatSeconds(840)).toBe("0.84 s");
    expect(formatSeconds(1962)).toBe("1.96 s");
  });

  it("shows a dash when there is no value", () => {
    expect(formatSeconds(null)).toBe("—");
  });
});

describe("tabFromHash", () => {
  it("opens the dashboard for #dashboard", () => {
    expect(tabFromHash("#dashboard")).toBe("dashboard");
  });

  it("falls back to chat for anything else", () => {
    expect(tabFromHash("")).toBe("chat");
    expect(tabFromHash("#nope")).toBe("chat");
  });
});
