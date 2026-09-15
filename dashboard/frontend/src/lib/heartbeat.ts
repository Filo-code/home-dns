import type { IncidentEventView } from "../api/types";

export type DaySeverity = "ok" | "warning" | "critical" | "unknown";

export interface HeartbeatDay {
  date: string; // YYYY-MM-DD (UTC)
  severity: DaySeverity;
}

/**
 * Reconstructs a day-by-day timeline from persisted opened/recovered events. There is no
 * continuous incident-state log, only discrete transitions (see the `incident_events` table
 * doc) — so a day before the first ever recorded event is genuinely "unknown", never assumed
 * healthy just because nothing was seen.
 */
export function buildHeartbeat(
  events: IncidentEventView[],
  days: number,
  now: Date = new Date()
): HeartbeatDay[] {
  const dayKey = (iso: string) => iso.slice(0, 10);
  const startDate = new Date(now);
  startDate.setUTCDate(startDate.getUTCDate() - (days - 1));
  startDate.setUTCHours(0, 0, 0, 0);

  const timeline: HeartbeatDay[] = [];
  for (let i = 0; i < days; i += 1) {
    const d = new Date(startDate);
    d.setUTCDate(d.getUTCDate() + i);
    timeline.push({ date: dayKey(d.toISOString()), severity: "unknown" });
  }

  const sorted = [...events].sort(
    (a, b) => new Date(a.occurred_at).getTime() - new Date(b.occurred_at).getTime()
  );
  if (sorted.length === 0) return timeline;

  const firstEventDay = dayKey(sorted[0]!.occurred_at);
  const openSeverity = new Map<string, "warning" | "critical">();
  let eventIndex = 0;

  for (const day of timeline) {
    while (eventIndex < sorted.length && dayKey(sorted[eventIndex]!.occurred_at) <= day.date) {
      const event = sorted[eventIndex]!;
      if (event.transition === "opened") {
        openSeverity.set(
          event.check_name,
          event.severity === "critical" ? "critical" : "warning"
        );
      } else {
        openSeverity.delete(event.check_name);
      }
      eventIndex += 1;
    }
    if (day.date < firstEventDay) {
      day.severity = "unknown";
    } else if (openSeverity.size > 0) {
      day.severity = [...openSeverity.values()].includes("critical") ? "critical" : "warning";
    } else {
      day.severity = "ok";
    }
  }

  return timeline;
}
