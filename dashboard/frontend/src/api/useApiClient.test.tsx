import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "../context/AuthContext";
import { installMockFetch, jsonResponse } from "../test-utils/mockFetch";
import { useApiClient } from "./useApiClient";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.pushState(null, "", "/");
});

function useTestSubject() {
  const auth = useAuth();
  const client = useApiClient();
  return { auth, client };
}

/** Boots AuthProvider to "authenticated" with a known CSRF token before the test's own calls. */
async function renderAuthenticated(initialCsrf = "csrf-initial") {
  installMockFetch([
    jsonResponse(200, { username: "anna", role: "admin", csrf_token: initialCsrf }),
  ]);
  const rendered = renderHook(() => useTestSubject(), { wrapper: AuthProvider });
  await waitFor(() => expect(rendered.result.current.auth.state.status).toBe("authenticated"));
  return rendered;
}

describe("useApiClient.get", () => {
  it("returns data on success", async () => {
    const { result } = await renderAuthenticated();
    installMockFetch([jsonResponse(200, { total: 42 })]);
    const data = await result.current.client.get<{ total: number }>("/api/v1/overview");
    expect(data).toEqual({ total: 42 });
  });

  it("on 401, clears auth state and redirects to /login preserving the path", async () => {
    window.history.pushState(null, "", "/devices/7");
    const { result } = await renderAuthenticated();
    installMockFetch([jsonResponse(401, { detail: "not authenticated" })]);
    await expect(result.current.client.get("/api/v1/devices/7")).rejects.toMatchObject({
      status: 401,
    });
    await waitFor(() => expect(result.current.auth.state.status).toBe("anonymous"));
    expect(window.location.pathname).toBe("/login");
    expect(window.location.search).toBe("?next=%2Fdevices%2F7");
  });

  it("propagates a 403 (permission) without touching auth state", async () => {
    const { result } = await renderAuthenticated();
    installMockFetch([jsonResponse(403, { detail: "admin role required" })]);
    await expect(result.current.client.get("/api/v1/queries")).rejects.toMatchObject({
      status: 403,
    });
    expect(result.current.auth.state.status).toBe("authenticated");
  });
});

describe("useApiClient.mutate", () => {
  it("sends the current CSRF token", async () => {
    const { result } = await renderAuthenticated("csrf-abc");
    const { calls } = installMockFetch([jsonResponse(200, { ok: true })]);
    await result.current.client.mutate("/api/v1/devices/1", "PATCH", { custom_name: "x" });
    const headers = calls[0]?.init?.headers as Record<string, string>;
    expect(headers["X-CSRF-Token"]).toBe("csrf-abc");
  });

  it("on a CSRF-failure 403, refreshes the session once and retries the mutation once", async () => {
    const { result } = await renderAuthenticated("stale-csrf");
    const { calls } = installMockFetch([
      jsonResponse(403, { detail: "CSRF token missing or invalid" }), // first attempt
      jsonResponse(200, { username: "anna", role: "admin", csrf_token: "fresh-csrf" }), // refresh
      jsonResponse(200, { ok: true }), // retried mutation
    ]);
    const data = await result.current.client.mutate<{ ok: boolean }>(
      "/api/v1/devices/1",
      "PATCH",
      { custom_name: "x" },
    );
    expect(data).toEqual({ ok: true });
    expect(calls).toHaveLength(3);
    const firstHeaders = calls[0]?.init?.headers as Record<string, string>;
    const retryHeaders = calls[2]?.init?.headers as Record<string, string>;
    expect(firstHeaders["X-CSRF-Token"]).toBe("stale-csrf");
    expect(retryHeaders["X-CSRF-Token"]).toBe("fresh-csrf");
    await waitFor(() => expect(result.current.auth.state.csrfToken).toBe("fresh-csrf"));
  });

  it("never retries more than once, even if the retry also fails", async () => {
    const { result } = await renderAuthenticated("stale-csrf");
    const { calls } = installMockFetch([
      jsonResponse(403, { detail: "CSRF token missing or invalid" }),
      jsonResponse(200, { username: "anna", role: "admin", csrf_token: "fresh-csrf" }),
      jsonResponse(403, { detail: "CSRF token missing or invalid" }), // retry also fails
    ]);
    await expect(
      result.current.client.mutate("/api/v1/devices/1", "PATCH", { custom_name: "x" }),
    ).rejects.toMatchObject({ status: 403 });
    expect(calls).toHaveLength(3); // exactly one retry, not a loop
  });

  it("on 401, clears auth state and redirects instead of retrying", async () => {
    const { result } = await renderAuthenticated();
    installMockFetch([jsonResponse(401, { detail: "not authenticated" })]);
    await expect(
      result.current.client.mutate("/api/v1/devices/1", "PATCH", { custom_name: "x" }),
    ).rejects.toMatchObject({ status: 401 });
    await waitFor(() => expect(result.current.auth.state.status).toBe("anonymous"));
  });

  it("a non-CSRF 403 (role/permission) is returned as-is, not retried", async () => {
    const { result } = await renderAuthenticated();
    const { calls } = installMockFetch([jsonResponse(403, { detail: "admin role required" })]);
    await expect(
      result.current.client.mutate("/api/v1/devices/1", "PATCH", { custom_name: "x" }),
    ).rejects.toMatchObject({ status: 403, detail: "admin role required" });
    expect(calls).toHaveLength(1);
    expect(result.current.auth.state.status).toBe("authenticated");
  });
});
