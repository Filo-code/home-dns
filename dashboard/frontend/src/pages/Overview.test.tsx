import { cleanup, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderAuthenticatedPage } from "../test-utils/renderAuthenticated";
import { jsonResponse } from "../test-utils/mockFetch";
import { installMockFetch } from "../test-utils/mockFetch";
import { Overview } from "./Overview";

const EMPTY_HISTORY = jsonResponse(200, {
  resolution: "hour",
  since: "x",
  until: "y",
  device_id: null,
  points: [],
});

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
    ...overrides,
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Overview", () => {
  it("shows the loading state before data arrives", async () => {
    await renderAuthenticatedPage(<Overview />, { responses: [] });
    expect(screen.getByText("Caricamento…")).toBeTruthy();
  });

  it("renders DNS status, 24h counters and system metrics", async () => {
    await renderAuthenticatedPage(<Overview />, { responses: [overview(), EMPTY_HISTORY] });
    await waitFor(() => expect(screen.getByRole("heading", { name: "Panoramica" })).toBeTruthy());
    expect(screen.getByText(/Servizio DNS: attivo/)).toBeTruthy();
    expect(screen.getByText("1000")).toBeTruthy(); // Intl "min2" grouping: 4 digits, 1 leading
    expect(screen.getByText("20%")).toBeTruthy();
    expect(screen.getByText(/45\.0 °C/)).toBeTruthy();
  });

  it("shows a fallback message instead of crashing when the provider is down", async () => {
    await renderAuthenticatedPage(<Overview />, {
      responses: [
        overview({ system: null, provider: { name: "mock", status: "down" } }),
        EMPTY_HISTORY,
      ],
    });
    await waitFor(() => expect(screen.getByText(/Dati di sistema non disponibili/)).toBeTruthy());
    expect(screen.getByText(/Servizio DNS: non risponde/)).toBeTruthy();
  });

  it('shows "in attesa" when metrics_as_of is still null', async () => {
    await renderAuthenticatedPage(<Overview />, {
      responses: [overview({ metrics_as_of: null }), EMPTY_HISTORY],
    });
    await waitFor(() =>
      expect(screen.getByText(/In attesa dei primi dati aggregati/)).toBeTruthy(),
    );
  });

  it("shows an error state with retry on failure, and retry recovers", async () => {
    await renderAuthenticatedPage(<Overview />, { responses: [{ status: 503 }, { status: 503 }] });
    await waitFor(() => screen.getByRole("alert"));
    expect(screen.getByRole("alert").textContent).toContain("Il servizio DNS non risponde");

    installMockFetch([overview(), EMPTY_HISTORY]);
    screen.getByRole("button", { name: "Riprova" }).click();
    await waitFor(() => expect(screen.getByRole("heading", { name: "Panoramica" })).toBeTruthy());
  });
});
