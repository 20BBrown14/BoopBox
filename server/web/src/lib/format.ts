const SECOND = 1;
const MINUTE = 60 * SECOND;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

// Largest first. Months and years are approximate, which is fine for a hint.
const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * DAY],
  ["month", 30 * DAY],
  ["week", 7 * DAY],
  ["day", DAY],
  ["hour", HOUR],
  ["minute", MINUTE],
  ["second", SECOND],
];

/** A stored UTC timestamp in the given language, in local time unless `timeZone` is set. */
export function formatDateTime(
  iso: string,
  lang: string,
  timeZone?: string,
): string {
  return new Intl.DateTimeFormat(lang, {
    dateStyle: "medium",
    timeStyle: "medium",
    timeZone,
  }).format(new Date(iso));
}

/** "3 minutes ago", "in 2 days", "yesterday": the largest unit that fits. */
export function formatRelative(iso: string, now: Date, lang: string): string {
  const seconds = (new Date(iso).getTime() - now.getTime()) / 1000;
  const format = new Intl.RelativeTimeFormat(lang, { numeric: "auto" });
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) {
      // Truncated, not rounded, so 59.6 minutes stays "59 minutes".
      return format.format(Math.trunc(seconds / size), unit);
    }
  }
  return format.format(0, "second");
}
