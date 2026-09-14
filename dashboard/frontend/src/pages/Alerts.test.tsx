import { cleanup, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse } from "../test-utils/mockFetch";
import { renderAuthenticatedPage } from "../test-utils/renderAuthenticated";
import { Alerts } from "./Alerts";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Alerts", () => {
  it("shows the empty state when there are no open incidents", async () => {
    await renderAuthenticatedPage(<Alerts />, { responses: [jsonResponse(200, [])] });
    await waitFor(() => expect(screen.getByText("Nessun incidente attivo.")).toBeTruthy());
  });

  it("renders incidents with a severity badge and timestamps", async () => {
    await renderAuthenticatedPage(<Alerts />, {
      responses: [
        jsonResponse(200, [
          {
            check_name: "storage_above_90",
            state: "incident",
            opened_at: "2026-09-14T09:00:00Z",
            last_change_at: "2026-09-14T09:30:00Z",
          },
        ]),
      ],
    });
    await waitFor(() => expect(screen.getByText("storage_above_90")).toBeTruthy());
    expect(screen.getByText("incidente")).toBeTruthy();
  });

  it("shows an error state on failure", async () => {
    await renderAuthenticatedPage(<Alerts />, { responses: [{ status: 503 }] });
    await waitFor(() => screen.getByRole("alert"));
  });
});
