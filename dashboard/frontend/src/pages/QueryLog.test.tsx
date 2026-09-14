import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse } from "../test-utils/mockFetch";
import { renderAuthenticatedPage } from "../test-utils/renderAuthenticated";
import { QueryLog } from "./QueryLog";

function page(entries: unknown[], nextCursor: string | null = null) {
  return jsonResponse(200, { entries, next_cursor: nextCursor });
}

const ENTRY_1 = {
  id: 1,
  time: "2026-09-14T10:00:00Z",
  client_address: "192.0.2.10",
  domain: "search.example",
  query_type: "A",
  outcome: "forwarded",
  blocked_by: null,
  latency_ms: 3,
};
const ENTRY_2 = {
  id: 2,
  time: "2026-09-14T09:00:00Z",
  client_address: "192.0.2.11",
  domain: "ads.example",
  query_type: "A",
  outcome: "blocked",
  blocked_by: "hagezi-multi-pro",
  latency_ms: 0.2,
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("QueryLog", () => {
  it("loads and shows results on mount", async () => {
    await renderAuthenticatedPage(<QueryLog />, { responses: [page([ENTRY_1])] });
    await waitFor(() => expect(screen.getByText("search.example")).toBeTruthy());
  });

  it("shows the empty state when there are no results", async () => {
    await renderAuthenticatedPage(<QueryLog />, { responses: [page([])] });
    await waitFor(() => expect(screen.getByText("Nessun dato ancora disponibile.")).toBeTruthy());
  });

  it("re-queries with the chosen filters on submit", async () => {
    const { calls } = await renderAuthenticatedPage(<QueryLog />, {
      responses: [page([ENTRY_1]), page([ENTRY_2])],
    });
    await waitFor(() => expect(screen.getByText("search.example")).toBeTruthy());

    fireEvent.change(screen.getByLabelText("Dominio"), { target: { value: "ads.example" } });
    fireEvent.change(screen.getByLabelText("Esito"), { target: { value: "blocked" } });
    fireEvent.click(screen.getByRole("button", { name: "Filtra" }));

    await waitFor(() => expect(screen.getByText("ads.example")).toBeTruthy());
    expect(screen.queryByText("search.example")).toBeNull(); // replaced, not appended
    const lastCall = calls[calls.length - 1]?.url ?? "";
    expect(lastCall).toContain("domain=ads.example");
    expect(lastCall).toContain("outcome=blocked");
  });

  it('"Carica altri" appends the next page instead of replacing results', async () => {
    await renderAuthenticatedPage(<QueryLog />, {
      responses: [page([ENTRY_1], "cursor-1"), page([ENTRY_2], null)],
    });
    await waitFor(() => expect(screen.getByText("search.example")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Carica altri" }));
    await waitFor(() => expect(screen.getByText("ads.example")).toBeTruthy());
    expect(screen.getByText("search.example")).toBeTruthy(); // still there — appended
    expect(screen.queryByRole("button", { name: "Carica altri" })).toBeNull(); // no more pages
  });

  it("never persists results to localStorage or sessionStorage", async () => {
    await renderAuthenticatedPage(<QueryLog />, { responses: [page([ENTRY_1])] });
    await waitFor(() => expect(screen.getByText("search.example")).toBeTruthy());
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it("shows an error state on failure", async () => {
    await renderAuthenticatedPage(<QueryLog />, { responses: [{ status: 503 }] });
    await waitFor(() => screen.getByRole("alert"));
  });
});
