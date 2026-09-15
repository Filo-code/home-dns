import { describe, expect, it } from "vitest";

import type { IncidentEventView } from "../api/types";
import { buildHeartbeat } from "./heartbeat";

const NOW = new Date("2026-09-14T12:00:00Z");

function event(
  transition: "opened" | "recovered",
  occurred_at: string,
  severity: IncidentEventView["severity"] = null,
  check_name = "storage"
): IncidentEventView {
  return { check_name, transition, occurred_at, severity };
}

describe("buildHeartbeat", () => {
  it("marks every day unknown when there are no events", () => {
    const days = buildHeartbeat([], 5, NOW);
    expect(days).toHaveLength(5);
    expect(days.every((d) => d.severity === "unknown")).toBe(true);
    expect(days[days.length - 1]!.date).toBe("2026-09-14");
  });

  it("marks days before the first event unknown, then ok, then incident, then ok again", () => {
    const events = [
      event("opened", "2026-09-12T04:00:00Z", "critical"),
      event("recovered", "2026-09-13T04:00:00Z"),
    ];
    const days = buildHeartbeat(events, 5, NOW);
    const byDate = Object.fromEntries(days.map((d) => [d.date, d.severity]));
    expect(byDate["2026-09-10"]).toBe("unknown"); // before any event was ever recorded
    expect(byDate["2026-09-11"]).toBe("unknown"); // still before the first recorded event
    expect(byDate["2026-09-12"]).toBe("critical"); // opened that day
    expect(byDate["2026-09-13"]).toBe("ok"); // recovered that day
    expect(byDate["2026-09-14"]).toBe("ok");
  });

  it("shows critical when any of multiple open checks is critical", () => {
    const events = [
      event("opened", "2026-09-14T01:00:00Z", "warning", "storage"),
      event("opened", "2026-09-14T02:00:00Z", "critical", "dns_down"),
    ];
    const days = buildHeartbeat(events, 1, NOW);
    expect(days[0]!.severity).toBe("critical");
  });

  it("treats a null severity on an open incident as warning, not ok or unknown", () => {
    const days = buildHeartbeat([event("opened", "2026-09-14T01:00:00Z", null)], 1, NOW);
    expect(days[0]!.severity).toBe("warning");
  });
});
