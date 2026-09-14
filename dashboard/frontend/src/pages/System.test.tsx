import { cleanup, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse } from "../test-utils/mockFetch";
import { renderAuthenticatedPage } from "../test-utils/renderAuthenticated";
import { System } from "./System";

function overview(system: Record<string, unknown> | null) {
  return jsonResponse(200, {
    provider: { name: "mock", status: "ok" },
    metrics_as_of: null,
    window_start: "x",
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
    system,
    open_incidents: 0,
    last_backup_at: null,
    last_blocklist_update_at: null,
  });
}

const CONFIG = jsonResponse(200, {
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
      logs_max_bytes: 1,
      logs_backup_count: 1,
      temp_max_age_hours: 1,
      backups_keep: 7,
      query_history_days: 30,
    },
  },
  metrics: {
    poll_interval_seconds: 60,
    flush_interval_seconds: 300,
    timezone: "Europe/Rome",
    minute_retention_hours: 48,
    hour_retention_days: 30,
    day_retention_days: 365,
  },
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("System", () => {
  it("shows CPU/RAM/storage details when the provider is up", async () => {
    await renderAuthenticatedPage(<System />, {
      responses: [
        overview({
          uptime_seconds: 3661,
          cpu_percent: 5,
          load_1m: 0.1,
          memory_total_bytes: 1000,
          memory_used_bytes: 500,
          temperature_celsius: 40,
          collected_at: "x",
        }),
        CONFIG,
      ],
    });
    await waitFor(() => expect(screen.getByText(/CPU: 5%/)).toBeTruthy());
    await waitFor(() => expect(screen.getByText("90%")).toBeTruthy()); // emergency threshold
    expect(screen.getByText("30 giorni")).toBeTruthy();
  });

  it("shows a fallback when the provider is down instead of crashing", async () => {
    await renderAuthenticatedPage(<System />, { responses: [overview(null), CONFIG] });
    await waitFor(() => expect(screen.getByText(/Dati di sistema non disponibili/)).toBeTruthy());
  });

  it("shows an error state on failure", async () => {
    await renderAuthenticatedPage(<System />, { responses: [{ status: 503 }] });
    await waitFor(() => screen.getByRole("alert"));
  });
});
