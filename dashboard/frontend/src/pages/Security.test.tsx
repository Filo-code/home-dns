import { cleanup, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse } from "../test-utils/mockFetch";
import { renderAuthenticatedPage } from "../test-utils/renderAuthenticated";
import { Security } from "./Security";

const CONFIG = jsonResponse(200, {
  dns_provider: "mock",
  notifier: "mock",
  groups: [],
  policies: [],
  blocklist_sources: [
    {
      id: "hagezi-multi-pro",
      name: "HaGeZi Multi PRO",
      categories: ["advertising", "tracking", "malware"],
      update_interval_hours: 24,
      last_activated_at: "2026-09-14T00:00:00Z",
    },
  ],
  storage: { thresholds_percent: {}, retention: {} },
  metrics: {},
});

const OVERVIEW = jsonResponse(200, {
  provider: { name: "mock", status: "ok" },
  metrics_as_of: null,
  window_start: "x",
  last_24h: {
    total: 100,
    blocked: 30,
    allowed: 70,
    cached: 0,
    forwarded: 70,
    block_percentage: 30,
    cache_hit_ratio: null,
    latency_p50_ms: null,
    latency_p95_ms: null,
    blocked_by_source: { "hagezi-multi-pro": 30 },
  },
  queries_per_second: 0,
  system: null,
  open_incidents: 0,
  last_backup_at: null,
  last_blocklist_update_at: "2026-09-14T04:00:00Z",
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Security", () => {
  it("shows blocklist sources with their per-source blocked count, not a fabricated per-category count", async () => {
    await renderAuthenticatedPage(<Security />, {
      responses: [CONFIG, OVERVIEW, jsonResponse(200, [])],
    });
    await waitFor(() => expect(screen.getByText("HaGeZi Multi PRO")).toBeTruthy());
    expect(screen.getByText("advertising, tracking, malware")).toBeTruthy();
    expect(screen.getByText("30")).toBeTruthy(); // the one per-source count, not per-category
    expect(screen.getByText("Nessun incidente attivo.")).toBeTruthy();
    // Per-source freshness column: a real timestamp renders as relative time, never "mai".
    expect(screen.getByText(/fa$/)).toBeTruthy();
  });

  it("shows 'mai' for a source that has never been activated", async () => {
    await renderAuthenticatedPage(<Security />, {
      responses: [
        jsonResponse(200, {
          ...(CONFIG.body as Record<string, unknown>),
          blocklist_sources: [
            {
              id: "hagezi-tif-mini",
              name: "HaGeZi TIF Mini",
              categories: ["malware"],
              update_interval_hours: 24,
              last_activated_at: null,
            },
          ],
        }),
        OVERVIEW,
        jsonResponse(200, []),
      ],
    });
    await waitFor(() => expect(screen.getByText("HaGeZi TIF Mini")).toBeTruthy());
    expect(screen.getByText("mai")).toBeTruthy();
  });

  it("shows security incidents when present", async () => {
    await renderAuthenticatedPage(<Security />, {
      responses: [
        CONFIG,
        OVERVIEW,
        jsonResponse(200, [
          {
            check_name: "dns_down",
            state: "incident",
            opened_at: "2026-09-14T09:00:00Z",
            last_change_at: "2026-09-14T09:00:00Z",
          },
        ]),
      ],
    });
    await waitFor(() => expect(screen.getByText("dns_down")).toBeTruthy());
    expect(screen.getByText("incidente")).toBeTruthy();
  });

  it("shows an error state when config fails to load", async () => {
    await renderAuthenticatedPage(<Security />, { responses: [{ status: 503 }] });
    await waitFor(() => screen.getByRole("alert"));
  });
});
