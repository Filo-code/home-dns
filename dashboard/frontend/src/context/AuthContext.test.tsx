import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { installMockFetch, jsonResponse } from "../test-utils/mockFetch";
import { AuthProvider, useAuth } from "./AuthContext";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function Probe() {
  const { state } = useAuth();
  return (
    <div>
      <span data-testid="status">{state.status}</span>
      <span data-testid="username">{state.username ?? ""}</span>
      <span data-testid="role">{state.role ?? ""}</span>
      <span data-testid="csrf">{state.csrfToken ?? ""}</span>
    </div>
  );
}

describe("AuthProvider", () => {
  it("starts loading, then becomes authenticated on a 200 session response", async () => {
    installMockFetch([
      jsonResponse(200, { username: "anna", role: "admin", csrf_token: "tok-1" }),
    ]);
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    expect(screen.getByTestId("status").textContent).toBe("loading");
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("authenticated"));
    expect(screen.getByTestId("username").textContent).toBe("anna");
    expect(screen.getByTestId("role").textContent).toBe("admin");
    expect(screen.getByTestId("csrf").textContent).toBe("tok-1");
  });

  it("becomes anonymous on a 401 session response", async () => {
    installMockFetch([jsonResponse(401, { detail: "not authenticated" })]);
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("anonymous"));
    expect(screen.getByTestId("username").textContent).toBe("");
  });

  it("falls back to the login page on a non-401 boot failure, never stuck loading", async () => {
    installMockFetch([{ status: 503 }]);
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("anonymous"));
  });
});
