import { cleanup, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse } from "../test-utils/mockFetch";
import { renderAuthenticatedPage } from "../test-utils/renderAuthenticated";
import { DeviceDetail } from "./DeviceDetail";

const DEVICE = jsonResponse(200, {
  device_id: 1,
  name: "pc-01.example",
  custom_name: null,
  hostname: "pc-01.example",
  mac: "00:00:5e:00:53:10",
  addresses: ["192.0.2.10"],
  group_id: "DEFAULT",
  first_seen: "2026-09-01T00:00:00Z",
  last_seen: "2026-09-14T10:00:00Z",
  last_24h: {
    total: 500,
    blocked: 50,
    allowed: 450,
    cached: 200,
    forwarded: 250,
    block_percentage: 10,
    cache_hit_ratio: 0.44,
    latency_p50_ms: 5,
    latency_p95_ms: 15,
    blocked_by_source: {},
  },
});

const HISTORY = jsonResponse(200, {
  resolution: "hour",
  since: "x",
  until: "y",
  device_id: 1,
  points: [],
});

const ACTIVITY = jsonResponse(200, {
  device_id: 1,
  since: "2026-09-13T10:00:00Z",
  truncated: true,
  top_domains: [{ domain: "search.example", count: 40 }],
  top_blocked: [{ domain: "ads.example", count: 10 }],
  recent: [
    {
      id: 1,
      time: "2026-09-14T10:00:00Z",
      client_address: "192.0.2.10",
      domain: "search.example",
      query_type: "A",
      outcome: "forwarded",
      blocked_by: null,
      latency_ms: 3.2,
    },
  ],
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("DeviceDetail", () => {
  it("shows a 404 error state for an invalid id, without calling the API", async () => {
    const { calls } = await renderAuthenticatedPage(<DeviceDetail deviceId="not-a-number" />, {
      responses: [],
    });
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(screen.getByRole("alert").textContent).toContain("Risorsa non trovata.");
    expect(calls.some((c) => c.url.includes("/devices/"))).toBe(false);
  });

  it("admin sees device info, history and admin activity (including the truncated notice)", async () => {
    await renderAuthenticatedPage(<DeviceDetail deviceId="1" />, {
      role: "admin",
      responses: [DEVICE, HISTORY, ACTIVITY],
    });
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "pc-01.example" })).toBeTruthy(),
    );
    expect(screen.getByText("00:00:5e:00:53:10")).toBeTruthy();
    // "search.example" legitimately appears twice: once in "top domains", once in "recent".
    await waitFor(() => expect(screen.getAllByText("search.example").length).toBe(2));
    expect(screen.getByText("ads.example")).toBeTruthy();
    expect(screen.getByText(/Mostrati solo i risultati più recenti/)).toBeTruthy();
  });

  it("viewer sees a permission-denied activity card and the admin endpoint is never called", async () => {
    const { calls } = await renderAuthenticatedPage(<DeviceDetail deviceId="1" />, {
      role: "viewer",
      responses: [DEVICE, HISTORY],
    });
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "pc-01.example" })).toBeTruthy(),
    );
    expect(screen.queryByText("00:00:5e:00:53:10")).toBeNull(); // MAC is admin-only
    expect(screen.getByText("Non hai i permessi per questa sezione.")).toBeTruthy();
    expect(calls.some((c) => c.url.includes("/activity"))).toBe(false);
  });
});
