import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse } from "../test-utils/mockFetch";
import { renderAuthenticatedPage } from "../test-utils/renderAuthenticated";
import { Devices } from "./Devices";

const DEVICE = {
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
};

const CONFIG = jsonResponse(200, {
  dns_provider: "mock",
  notifier: "mock",
  groups: [
    { id: "DEFAULT", description: "d", policy: "standard" },
    { id: "GAMING", description: "g", policy: "gaming" },
  ],
  policies: [],
  blocklist_sources: [],
  storage: { thresholds_percent: {}, retention: {} },
  metrics: {},
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Devices", () => {
  it("shows the empty state when there are no devices", async () => {
    await renderAuthenticatedPage(<Devices />, { responses: [jsonResponse(200, [])] });
    await waitFor(() => expect(screen.getByText("Nessun dato ancora disponibile.")).toBeTruthy());
  });

  it("viewer sees no MAC column and no edit controls", async () => {
    await renderAuthenticatedPage(<Devices />, {
      role: "viewer",
      responses: [jsonResponse(200, [DEVICE])],
    });
    await waitFor(() => expect(screen.getByText("pc-01.example")).toBeTruthy());
    expect(screen.queryByText("00:00:5e:00:53:10")).toBeNull();
    expect(screen.queryByText("Rinomina")).toBeNull();
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  it("admin sees the MAC column and can change a device's group", async () => {
    const { calls } = await renderAuthenticatedPage(<Devices />, {
      role: "admin",
      responses: [
        jsonResponse(200, [DEVICE]),
        CONFIG,
        jsonResponse(200, { ok: true }),
        jsonResponse(200, [{ ...DEVICE, group_id: "GAMING" }]),
      ],
    });
    await waitFor(() => expect(screen.getByText("00:00:5e:00:53:10")).toBeTruthy());
    await waitFor(() => expect(screen.getByRole("combobox")).toBeTruthy());

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "GAMING" } });
    await waitFor(() =>
      expect(calls.some((c) => c.url === "/api/v1/devices/1" && c.init?.method === "PATCH")).toBe(
        true,
      ),
    );
    const patchCall = calls.find((c) => c.init?.method === "PATCH");
    expect(JSON.parse(patchCall?.init?.body as string)).toEqual({ group_id: "GAMING" });
  });

  it("admin can rename a device via the inline form", async () => {
    const { calls } = await renderAuthenticatedPage(<Devices />, {
      role: "admin",
      responses: [
        jsonResponse(200, [DEVICE]),
        CONFIG,
        jsonResponse(200, { ok: true }),
        jsonResponse(200, [{ ...DEVICE, custom_name: "PC Studio" }]),
      ],
    });
    await waitFor(() => expect(screen.getByText("Rinomina")).toBeTruthy());
    fireEvent.click(screen.getByText("Rinomina"));
    const input = screen.getByLabelText("Nome personalizzato per pc-01.example");
    fireEvent.change(input, { target: { value: "PC Studio" } });
    fireEvent.click(screen.getByRole("button", { name: "Salva" }));
    await waitFor(() => expect(calls.some((c) => c.init?.method === "PATCH")).toBe(true));
    const patchCall = calls.find((c) => c.init?.method === "PATCH");
    expect(JSON.parse(patchCall?.init?.body as string)).toEqual({ custom_name: "PC Studio" });
  });

  it("shows an error state on failure", async () => {
    await renderAuthenticatedPage(<Devices />, { responses: [{ status: 503 }] });
    await waitFor(() => screen.getByRole("alert"));
  });
});
