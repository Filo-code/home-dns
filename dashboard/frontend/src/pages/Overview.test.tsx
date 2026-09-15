import { cleanup, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderAuthenticatedPage } from "../test-utils/renderAuthenticated";
import { jsonResponse } from "../test-utils/mockFetch";
import { Overview } from "./Overview";

const EMPTY_HISTORY = jsonResponse(200, {
  resolution: "hour",
  since: "x",
  until: "y",
  device_id: null,
  points: [],
});

const EMPTY_INCIDENTS = jsonResponse(200, []);
const EMPTY_DEVICES = jsonResponse(200, []);

function overview(overrides: Record<string, unknown> = {}) {
  return jsonResponse(200, {
    provider: { name: "mock", status: "ok" },
    metrics_as_of: "2026-09-14T10:00:00Z",
    window_start: "2026-09-13T10:00:00Z",
    last_24h: {
      total: 1000,
      blocked: 200,
      allowed: 800,
      cached: 400,
      forwarded: 400,
      block_percentage: 20,
      cache_hit_ratio: 0.5,
      latency_p50_ms: 5,
      latency_p95_ms: 20,
      blocked_by_source: { "hagezi-multi-pro": 180, "hagezi-tif-mini": 20 },
    },
    queries_per_second: 3.5,
    system: {
      uptime_seconds: 90000,
      cpu_percent: 12.5,
      load_1m: 0.3,
      memory_total_bytes: 4 * 1024 * 1024 * 1024,
      memory_used_bytes: 1 * 1024 * 1024 * 1024,
      temperature_celsius: 45,
      collected_at: "2026-09-14T10:00:00Z",
    },
    open_incidents: 2,
    last_backup_at: "2026-09-14T03:00:00Z",
    last_blocklist_update_at: "2026-09-14T04:00:00Z",
    storage: {
      total_bytes: 1_000_000,
      used_bytes: 300_000,
      free_bytes: 700_000,
      used_percent: 30,
    },
    ...overrides,
  });
}

function config(overrides: Record<string, unknown> = {}) {
  return jsonResponse(200, {
    dns_provider: "mock",
    notifier: "mock",
    groups: [],
    policies: [],
    blocklist_sources: [
      {
        id: "hagezi-multi-pro",
        name: "HaGeZi Multi PRO",
        categories: ["advertising"],
        update_interval_hours: 24,
        last_activated_at: "2026-09-14T04:00:00Z",
      },
    ],
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
    ...overrides,
  });
}

/** Overview's effects fire in this order after the session: its own three mount-only fetches
 * (history, incident history, devices — issued synchronously in that order inside one effect)
 * as OverviewProvider's child, then OverviewProvider's own polled overview fetch, then its
 * config fetch — see App.tsx/OverviewContext.tsx for why. */
function queueOverviewPage(overrides: Record<string, unknown> = {}) {
  return [EMPTY_HISTORY, EMPTY_INCIDENTS, EMPTY_DEVICES, overview(overrides), config()];
}

const NOOP = () => {};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Overview", () => {
  it("shows the loading state before data arrives", async () => {
    await renderAuthenticatedPage(<Overview role="admin" onRequestAdminAction={NOOP} />, {
      responses: [],
      withOverview: true,
    });
    expect(screen.getByText("Caricamento…")).toBeTruthy();
  });

  it("renders the health ring, ledger and 24h counters", async () => {
    await renderAuthenticatedPage(<Overview role="admin" onRequestAdminAction={NOOP} />, {
      responses: queueOverviewPage(),
      withOverview: true,
    });
    await waitFor(() => expect(screen.getByRole("heading", { name: "Panoramica" })).toBeTruthy());
    expect(screen.getByText("1000")).toBeTruthy(); // Intl "min2" grouping: 4 digits, 1 leading
    expect(screen.getByText("20%")).toBeTruthy();
    expect(screen.getByText(/45\.0 °C/)).toBeTruthy();
    expect(screen.getByText("DNS")).toBeTruthy(); // health ledger row label
  });

  it("shows the most active devices and a recent-activity summary from real data", async () => {
    const devices = jsonResponse(200, [
      {
        device_id: 1,
        name: "PC Studio",
        custom_name: "PC Studio",
        hostname: "pc-studio.example",
        mac: "00:00:5e:00:53:10",
        addresses: ["192.0.2.14"],
        group_id: "GAMING",
        first_seen: "2026-09-10T08:00:00Z",
        last_seen: "2026-09-14T09:59:00Z",
        last_24h: {
          total: 500,
          blocked: 50,
          allowed: 450,
          cached: 200,
          forwarded: 250,
          block_percentage: 10,
          cache_hit_ratio: 0.4,
          latency_p50_ms: 4,
          latency_p95_ms: 15,
          blocked_by_source: {},
        },
      },
      {
        device_id: 2,
        name: "iPad Cucina",
        custom_name: null,
        hostname: "ipad-cucina.example",
        mac: "00:00:5e:00:53:20",
        addresses: ["192.0.2.22"],
        group_id: "DEFAULT",
        first_seen: "2026-09-14T07:00:00Z",
        last_seen: "2026-09-14T09:50:00Z",
        last_24h: {
          total: 100,
          blocked: 10,
          allowed: 90,
          cached: 40,
          forwarded: 50,
          block_percentage: 10,
          cache_hit_ratio: 0.4,
          latency_p50_ms: 4,
          latency_p95_ms: 15,
          blocked_by_source: {},
        },
      },
    ]);
    const incidents = jsonResponse(200, [
      { check_name: "storage", transition: "opened", occurred_at: "2026-09-13T04:00:00Z", severity: "warning" },
    ]);
    await renderAuthenticatedPage(<Overview role="admin" onRequestAdminAction={NOOP} />, {
      responses: [EMPTY_HISTORY, incidents, devices, overview(), config()],
      withOverview: true,
    });
    await waitFor(() => expect(screen.getByRole("heading", { name: "Panoramica" })).toBeTruthy());
    expect(screen.getByText("PC Studio")).toBeTruthy(); // higher 24h total, listed
    expect(screen.getByText("iPad Cucina")).toBeTruthy();
    expect(screen.getByText(/Nuovo dispositivo rilevato: iPad Cucina/)).toBeTruthy();
    expect(screen.getByText(/Incidente storage aperto/)).toBeTruthy();
    expect(screen.getByText(/Backup completato/)).toBeTruthy();
  });

  it("shows a fallback message instead of crashing when the provider is down", async () => {
    await renderAuthenticatedPage(<Overview role="admin" onRequestAdminAction={NOOP} />, {
      responses: queueOverviewPage({ system: null, provider: { name: "mock", status: "down" } }),
      withOverview: true,
    });
    await waitFor(() => expect(screen.getByText(/Dati di sistema non disponibili/)).toBeTruthy());
  });

  it('shows "in attesa" when metrics_as_of is still null', async () => {
    await renderAuthenticatedPage(<Overview role="admin" onRequestAdminAction={NOOP} />, {
      responses: queueOverviewPage({ metrics_as_of: null }),
      withOverview: true,
    });
    await waitFor(() =>
      expect(screen.getByText(/In attesa dei primi dati aggregati/)).toBeTruthy(),
    );
  });

  it("hides the admin quick actions for a viewer", async () => {
    await renderAuthenticatedPage(<Overview role="viewer" onRequestAdminAction={NOOP} />, {
      responses: queueOverviewPage(),
      withOverview: true,
      role: "viewer",
    });
    await waitFor(() => expect(screen.getByRole("heading", { name: "Panoramica" })).toBeTruthy());
    expect(screen.queryByRole("button", { name: /Aggiorna blocklist/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Backup/ })).toBeNull();
  });

  it("shows an error state on failure", async () => {
    await renderAuthenticatedPage(<Overview role="admin" onRequestAdminAction={NOOP} />, {
      responses: [EMPTY_HISTORY, EMPTY_INCIDENTS, EMPTY_DEVICES, { status: 503 }, { status: 503 }],
      withOverview: true,
    });
    await waitFor(() => screen.getByRole("alert"));
    expect(screen.getByRole("alert").textContent).toContain("Il servizio DNS non risponde");
  });
});
