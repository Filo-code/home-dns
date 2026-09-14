import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "../context/AuthContext";
import { installMockFetch, jsonResponse } from "../test-utils/mockFetch";
import { Login } from "./Login";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.pushState(null, "", "/login");
});

function LoginWithState() {
  const { state } = useAuth();
  return (
    <>
      <span data-testid="status">{state.status}</span>
      <Login />
    </>
  );
}

async function fillAndSubmit(username: string, password: string) {
  fireEvent.change(screen.getByLabelText("Nome utente"), { target: { value: username } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: /accedi/i }));
}

describe("Login", () => {
  it("on success, authenticates and redirects to the intended path", async () => {
    window.history.pushState(null, "", "/login?next=%2Fsecurity");
    installMockFetch([jsonResponse(401, { detail: "not authenticated" })]); // boot check
    render(
      <AuthProvider>
        <LoginWithState />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("anonymous"));

    installMockFetch([
      jsonResponse(200, { username: "anna", role: "admin", csrf_token: "tok-1" }),
    ]);
    await fillAndSubmit("anna", "correct horse battery staple");

    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("authenticated"));
    expect(window.location.pathname).toBe("/security");
  });

  it("shows a generic invalid-credentials message on 401, never which field was wrong", async () => {
    window.history.pushState(null, "", "/login");
    installMockFetch([jsonResponse(401, { detail: "not authenticated" })]);
    render(
      <AuthProvider>
        <Login />
      </AuthProvider>,
    );
    installMockFetch([jsonResponse(401, { detail: "invalid username or password" })]);
    await fillAndSubmit("ghost", "wrong password");
    await waitFor(() => screen.getByRole("alert"));
    expect(screen.getByRole("alert").textContent).toBe("Credenziali non valide.");
  });

  it("shows the lockout message on 429", async () => {
    installMockFetch([jsonResponse(401, { detail: "not authenticated" })]);
    render(
      <AuthProvider>
        <Login />
      </AuthProvider>,
    );
    installMockFetch([jsonResponse(429, { detail: "too many failed logins" })]);
    await fillAndSubmit("anna", "whatever password");
    await waitFor(() => screen.getByRole("alert"));
    expect(screen.getByRole("alert").textContent).toBe(
      "Troppi tentativi, riprova tra qualche minuto.",
    );
  });

  it("shows an unreachable-server message on a network failure", async () => {
    installMockFetch([jsonResponse(401, { detail: "not authenticated" })]);
    render(
      <AuthProvider>
        <Login />
      </AuthProvider>,
    );
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("network down"))),
    );
    await fillAndSubmit("anna", "whatever password");
    await waitFor(() => screen.getByRole("alert"));
    expect(screen.getByRole("alert").textContent).toBe("Impossibile contattare il server.");
  });
});
