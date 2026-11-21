import { describe, expect, test } from "vitest";
import { formatDateTime, formatRelative } from "./format";

const NOW = new Date("2026-11-13T09:30:00.000Z");
const SECOND = 1000;
const MINUTE = 60 * SECOND;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

function offset(ms: number): string {
  return new Date(NOW.getTime() + ms).toISOString();
}

describe("formatRelative", () => {
  test.each([
    [0, "now"],
    [-30 * SECOND, "30 seconds ago"],
    [-59 * SECOND, "59 seconds ago"],
    [-60 * SECOND, "1 minute ago"],
    [-(59 * MINUTE + 59 * SECOND), "59 minutes ago"],
    [-HOUR, "1 hour ago"],
    [-23 * HOUR, "23 hours ago"],
    [-DAY, "yesterday"],
    [-6 * DAY, "6 days ago"],
    [-7 * DAY, "last week"],
    [-29 * DAY, "4 weeks ago"],
    [-30 * DAY, "last month"],
    [-364 * DAY, "12 months ago"],
    [-365 * DAY, "last year"],
    [-730 * DAY, "2 years ago"],
    [5 * MINUTE, "in 5 minutes"],
    [DAY, "tomorrow"],
    [3 * DAY, "in 3 days"],
  ])("%i ms → %s", (ms, expected) => {
    expect(formatRelative(offset(ms), NOW, "en")).toBe(expected);
  });

  test("follows the language", () => {
    expect(formatRelative(offset(-MINUTE), NOW, "de")).toBe("vor 1 Minute");
    expect(formatRelative(offset(-DAY), NOW, "de")).toBe("gestern");
  });
});

describe("formatDateTime", () => {
  const iso = "2026-11-13T09:30:00.000Z";

  test("formats in a given time zone", () => {
    expect(formatDateTime(iso, "en", "UTC")).toMatch(
      /^Nov 13, 2026, 9:30:00\sAM$/,
    );
    expect(formatDateTime(iso, "en", "Asia/Tokyo")).toMatch(
      /^Nov 13, 2026, 6:30:00\sPM$/,
    );
  });

  test("follows the language", () => {
    expect(formatDateTime(iso, "de", "UTC")).toBe("13.11.2026, 09:30:00");
  });

  test("uses the local time zone by default", () => {
    const local = new Intl.DateTimeFormat("en", {
      dateStyle: "medium",
      timeStyle: "medium",
    }).format(new Date(iso));
    expect(formatDateTime(iso, "en")).toBe(local);
  });
});
