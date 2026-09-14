import { describe, expect, it } from "vitest";

import {
  healthLabelIt,
  incidentLabelIt,
  severityFromHealth,
  severityFromIncident,
} from "./severity";

describe("severityFromHealth", () => {
  it.each([
    ["ok", "ok"],
    ["degraded", "warning"],
    ["down", "critical"],
  ] as const)("%s -> %s", (status, expected) => {
    expect(severityFromHealth(status)).toBe(expected);
  });
});

describe("severityFromIncident", () => {
  it.each([
    ["ok", "ok"],
    ["suspect", "warning"],
    ["recovering", "warning"],
    ["incident", "critical"],
  ] as const)("%s -> %s", (state, expected) => {
    expect(severityFromIncident(state)).toBe(expected);
  });
});

describe("Italian labels", () => {
  it("has one label per health status and incident state", () => {
    expect(healthLabelIt("ok")).toBe("attivo");
    expect(healthLabelIt("down")).toBe("non risponde");
    expect(incidentLabelIt("incident")).toBe("incidente");
    expect(incidentLabelIt("ok")).toBe("normale");
  });
});
