import { describe, expect, it } from "vitest";

import { formatBytes, formatLatency, formatNumber, formatPercent, formatUptime } from "./format";

describe("formatNumber / formatPercent", () => {
  it("uses Italian grouping/decimal conventions", () => {
    expect(formatNumber(12345)).toBe("12.345");
    expect(formatPercent(12.3456)).toBe("12,3%");
  });
});

describe("formatBytes", () => {
  it.each([
    [500, "500 B"],
    [2048, "2 KB"],
    [5 * 1024 * 1024, "5 MB"],
  ])("formats %s bytes as %s", (bytes, expected) => {
    expect(formatBytes(bytes)).toBe(expected);
  });
});

describe("formatUptime", () => {
  it("includes days only when there are any", () => {
    expect(formatUptime(90)).toBe("1m");
    expect(formatUptime(3661)).toBe("1h 1m");
    expect(formatUptime(90061)).toBe("1g 1h 1m");
  });
});

describe("formatLatency", () => {
  it("shows an em dash for null/undefined", () => {
    expect(formatLatency(null)).toBe("—");
    expect(formatLatency(undefined)).toBe("—");
  });

  it("switches to microseconds under 1ms", () => {
    expect(formatLatency(0.5)).toBe("500 µs");
    expect(formatLatency(12.5)).toBe("12,5 ms");
  });
});
