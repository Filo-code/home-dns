import { afterEach, describe, expect, it, vi } from "vitest";

import { installMockFetch, jsonResponse } from "../test-utils/mockFetch";
import { ApiError, apiFetch } from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiFetch", () => {
  it("returns parsed JSON for a successful response", async () => {
    installMockFetch([jsonResponse(200, { a: 1 })]);
    const result = await apiFetch<{ a: number }>("/api/v1/thing");
    expect(result).toEqual({ a: 1 });
  });

  it("returns undefined for a 204 response", async () => {
    installMockFetch([{ status: 204 }]);
    const result = await apiFetch<void>("/api/v1/thing", { method: "POST" });
    expect(result).toBeUndefined();
  });

  it("throws a typed ApiError with the server's detail on a non-2xx response", async () => {
    installMockFetch([jsonResponse(404, { detail: "device not found" })]);
    await expect(apiFetch("/api/v1/devices/999")).rejects.toMatchObject({
      status: 404,
      detail: "device not found",
    });
  });

  it("falls back to statusText when the body is not JSON", async () => {
    installMockFetch([{ status: 500, statusText: "Internal Server Error" }]);
    await expect(apiFetch("/api/v1/thing")).rejects.toMatchObject({
      status: 500,
      detail: "Internal Server Error",
    });
  });

  it("wraps a network failure as a status-0 ApiError, never a raw exception", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))),
    );
    await expect(apiFetch("/api/v1/thing")).rejects.toMatchObject({ status: 0 });
  });

  it("sends the CSRF header on unsafe methods only when a token is given", async () => {
    const { calls } = installMockFetch([jsonResponse(200, {}), jsonResponse(200, {})]);
    await apiFetch("/api/v1/devices/1", { method: "PATCH", csrfToken: "tok-123" });
    await apiFetch("/api/v1/overview", { csrfToken: "tok-123" }); // GET: must not send it
    const headers1 = calls[0]?.init?.headers as Record<string, string>;
    const headers2 = calls[1]?.init?.headers as Record<string, string>;
    expect(headers1["X-CSRF-Token"]).toBe("tok-123");
    expect(headers2["X-CSRF-Token"]).toBeUndefined();
  });

  it("sends JSON body with a Content-Type header for mutations", async () => {
    const { calls } = installMockFetch([jsonResponse(200, {})]);
    await apiFetch("/api/v1/devices/1", { method: "PATCH", body: { custom_name: "PC" } });
    expect(calls[0]?.init?.body).toBe(JSON.stringify({ custom_name: "PC" }));
    expect((calls[0]?.init?.headers as Record<string, string>)["Content-Type"]).toBe(
      "application/json",
    );
  });

  it("uses same-origin credentials", async () => {
    const { calls } = installMockFetch([jsonResponse(200, {})]);
    await apiFetch("/api/v1/overview");
    expect(calls[0]?.init?.credentials).toBe("same-origin");
  });

  it("builds a query string, dropping null/undefined values", async () => {
    const { calls } = installMockFetch([jsonResponse(200, {})]);
    await apiFetch("/api/v1/queries", {
      query: { domain: "x.example", outcome: undefined, limit: 10 },
    });
    expect(calls[0]?.url).toBe("/api/v1/queries?domain=x.example&limit=10");
  });

  it("stays a relative same-origin path — never an absolute URL to another host", async () => {
    const { calls } = installMockFetch([jsonResponse(200, {})]);
    await apiFetch("/api/v1/overview");
    expect(calls[0]?.url).toBe("/api/v1/overview");
  });
});

describe("ApiError.isCsrfFailure", () => {
  it("is true only for a 403 whose detail mentions CSRF", () => {
    expect(new ApiError(403, "CSRF token missing or invalid").isCsrfFailure).toBe(true);
    expect(new ApiError(403, "admin role required").isCsrfFailure).toBe(false);
    expect(new ApiError(401, "CSRF token missing or invalid").isCsrfFailure).toBe(false);
  });
});
