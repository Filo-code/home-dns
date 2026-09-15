import { describe, expect, it } from "vitest";

import type { ConfigView, OverviewResponse } from "../api/types";
import { computeHealth } from "./health";

const NOW = new Date("2026-09-14T10:00:00Z");

function overview(overrides: Partial<OverviewResponse> = {}): OverviewResponse {
  return {
    provider: { name: "mock", status: "ok" },
    metrics_as_of: "2026-09-14T09:59:00Z",
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
      blocked_by_source: {},
    },
    queries_per_second: 3.5,
    system: {
      uptime_seconds: 90000,
      cpu_percent: 12.5,
      load_1m: 0.3,
      memory_total_bytes: 4 * 1024 * 1024 * 1024,
      memory_used_bytes: 1 * 1024 * 1024 * 1024,
      temperature_celsius: 45,
      collected_at: "2026-09-14T09:59:00Z",
    },
    open_incidents: 0,
    last_backup_at: "2026-09-14T04:00:00Z",
    last_blocklist_update_at: "2026-09-14T04:00:00Z",
    storage: {
      total_bytes: 1_000_000,
      used_bytes: 500_000,
      free_bytes: 500_000,
      used_percent: 50,
    },
    ...overrides,
  };
}

function config(overrides: Partial<ConfigView> = {}): ConfigView {
  return {
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
  };
}

describe("computeHealth", () => {
  it("scores a fully healthy system in the Ottimo band", () => {
    const result = computeHealth(overview(), config(), NOW);
    expect(result.band).toBe("ottimo");
    expect(result.score).toBeGreaterThanOrEqual(90);
    expect(result.components).toHaveLength(5);
  });

  it("drops sharply when the DNS provider is down", () => {
    const down = computeHealth(
      overview({ provider: { name: "mock", status: "down" } }),
      config(),
      NOW
    );
    const healthy = computeHealth(overview(), config(), NOW);
    expect(down.score).toBeLessThan(healthy.score - 20);
    const dns = down.components.find((c) => c.id === "dns");
    expect(dns?.severity).toBe("critical");
  });

  it("scores blocklist freshness from the worst source, not the aggregate timestamp", () => {
    const staleConfig = config({
      blocklist_sources: [
        {
          id: "hagezi-multi-pro",
          name: "HaGeZi Multi PRO",
          categories: [],
          update_interval_hours: 24,
          last_activated_at: "2026-09-10T04:00:00Z", // 4 days stale
        },
      ],
    });
    const result = computeHealth(overview(), staleConfig, NOW);
    const blocklist = result.components.find((c) => c.id === "blocklist");
    expect(blocklist?.score).toBe(0);
    expect(blocklist?.severity).toBe("critical");
  });

  it("renormalizes weight instead of fabricating a score when system metrics are unavailable", () => {
    const result = computeHealth(overview({ system: null }), config(), NOW);
    expect(result.components.find((c) => c.id === "system")).toBeUndefined();
    expect(result.components).toHaveLength(4);
    expect(Number.isNaN(result.score)).toBe(false);
  });

  it("renormalizes weight when config (and thus blocklist freshness) is unavailable", () => {
    const result = computeHealth(overview(), null, NOW);
    expect(result.components.find((c) => c.id === "blocklist")).toBeUndefined();
    expect(result.components).toHaveLength(4);
  });

  it("clamps the open-incident penalty at 3 incidents / -15 points", () => {
    const three = computeHealth(overview({ open_incidents: 3 }), config(), NOW);
    const ten = computeHealth(overview({ open_incidents: 10 }), config(), NOW);
    expect(three.score).toBe(ten.score);
    const zero = computeHealth(overview({ open_incidents: 0 }), config(), NOW);
    expect(zero.score - three.score).toBe(15);
  });

  it("never returns a score outside [0, 100]", () => {
    const base = overview();
    const worst = computeHealth(
      overview({
        provider: { name: "mock", status: "down" },
        last_backup_at: null,
        open_incidents: 20,
        system: { ...base.system!, cpu_percent: 99, temperature_celsius: 90 },
      }),
      config({
        blocklist_sources: [
          {
            id: "x",
            name: "x",
            categories: [],
            update_interval_hours: 24,
            last_activated_at: null,
          },
        ],
      }),
      NOW
    );
    expect(worst.score).toBeGreaterThanOrEqual(0);
    expect(worst.score).toBeLessThanOrEqual(100);
    expect(worst.band).toBe("critico");
  });
});
