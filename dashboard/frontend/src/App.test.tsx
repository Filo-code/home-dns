import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { installMockFetch, jsonResponse } from "./test-utils/mockFetch";

const EMPTY_DEVICES = jsonResponse(200, []);

const EMPTY_OVERVIEW = jsonResponse(200, {
  provider: { name: "mock", status: "ok" },
  metrics_as_of: null,
  window_start: "2026-09-14T00:00:00Z",
  last_24h: {
    total: 0,
    blocked: 0,
    allowed: 0,
    cached: 0,
    forwarded: 0,
    block_percentage: 0,
    cache_hit_ratio: null,
    latency_p50_ms: null,
    latency_p95_ms: null,
    blocked_by_source: {},
  },
  queries_per_second: 0,
  system: null,
  open_incidents: 0,
  last_backup_at: null,
  last_blocklist_update_at: null,
  storage: { total_bytes: 0, used_bytes: 0, free_bytes: 0, used_percent: 0 },
});

const EMPTY_HISTORY = jsonResponse(200, {
  resolution: "hour",
  since: "2026-09-13T00:00:00Z",
  until: "2026-09-14T00:00:00Z",
  device_id: null,
  points: [],
});

const EMPTY_INCIDENTS = jsonResponse(200, []);

const EMPTY_CONFIG = jsonResponse(200, {
  dns_provider: "mock",
  notifier: "mock",
  groups: [],
  policies: [],
  blocklist_sources: [],
  storage: {
    thresholds_percent: {
      healthy_below: 70,
      warning_from: 70,
      auto_cleanup_from: 80,
      emergency_from: 90,
    },
    retention: {
      logs_max_bytes: 1024,
      logs_backup_count: 5,
      temp_max_age_hours: 24,
      backups_keep: 7,
      query_history_days: 30,
    },
  },
  metrics: {
    poll_interval_seconds: 30,
    flush_interval_seconds: 300,
    timezone: "Europe/Rome",
    minute_retention_hours: 24,
    hour_retention_days: 30,
    day_retention_days: 400,
  },
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.pushState(null, "", "/");
});

describe("App", () => {
  it("redirects an unauthenticated visitor to the login page", async () => {
    window.history.pushState(null, "", "/devices");
    installMockFetch([jsonResponse(401, { detail: "not authenticated" })]);
    render(<App />);
    await waitFor(() => expect(screen.getByRole("heading", { name: "Home DNS" })).toBeTruthy());
    expect(window.location.pathname).toBe("/login");
    expect(window.location.search).toBe("?next=%2Fdevices");
  });

  it("an authenticated visitor landing on /login is sent to the overview", async () => {
    window.history.pushState(null, "", "/login");
    // All responses this test needs, queued in one call — a second installMockFetch() call
    // partway through would race the pending boot effect and consume the wrong entry.
    installMockFetch([
      jsonResponse(200, { username: "anna", role: "admin", csrf_token: "t" }),
      EMPTY_HISTORY,
      EMPTY_INCIDENTS,
      EMPTY_OVERVIEW,
      EMPTY_CONFIG,
    ]);
    render(<App />);
    await waitFor(() => expect(window.location.pathname).toBe("/"));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Panoramica" })).toBeTruthy());
  });

  it("a viewer does not see the admin-only Registro query nav link", async () => {
    window.history.pushState(null, "", "/devices");
    installMockFetch([
      jsonResponse(200, { username: "famiglia", role: "viewer", csrf_token: "t" }),
      EMPTY_DEVICES,
    ]);
    render(<App />);
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Dispositivi" })).toBeTruthy(),
    );
    expect(screen.queryByText("Registro query")).toBeNull();
  });

  it("an admin does see the Registro query nav link", async () => {
    window.history.pushState(null, "", "/devices");
    installMockFetch([
      jsonResponse(200, { username: "anna", role: "admin", csrf_token: "t" }),
      EMPTY_DEVICES,
    ]);
    render(<App />);
    await waitFor(() => expect(screen.getByText("Registro query")).toBeTruthy());
  });

  it("a viewer at /queries sees a permission-denied state and the API is never called", async () => {
    window.history.pushState(null, "", "/queries");
    const { calls } = installMockFetch([
      jsonResponse(200, { username: "famiglia", role: "viewer", csrf_token: "t" }),
    ]);
    render(<App />);
    await waitFor(() =>
      expect(screen.getByText("Non hai i permessi per questa sezione.")).toBeTruthy(),
    );
    expect(calls.some((call) => call.url.includes("/api/v1/queries"))).toBe(false);
  });
});
