import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";
import { StatusBadge } from "./StatusBadge";

afterEach(cleanup);

describe("LoadingState", () => {
  it("shows the standard Italian copy by default", () => {
    render(<LoadingState />);
    expect(screen.getByText("Caricamento…")).toBeTruthy();
    expect(screen.getByRole("status")).toBeTruthy();
  });
});

describe("EmptyState", () => {
  it("shows the standard Italian copy by default", () => {
    render(<EmptyState />);
    expect(screen.getByText("Nessun dato ancora disponibile.")).toBeTruthy();
  });
});

describe("ErrorState", () => {
  it.each([
    [403, "Non hai i permessi per questa sezione."],
    [404, "Risorsa non trovata."],
    [429, "Troppi tentativi, riprova tra qualche minuto."],
    [503, "Il servizio DNS non risponde al momento."],
    [0, "Impossibile contattare il server."],
    [500, "Si è verificato un errore imprevisto."],
  ])("maps ApiError(%s) to Italian copy, never the raw detail", (status, message) => {
    render(<ErrorState error={new ApiError(status, "some internal detail nobody should see")} />);
    expect(screen.getByRole("alert").textContent).toContain(message);
    expect(screen.queryByText(/internal detail/)).toBeNull();
  });

  it("falls back to a generic message for a non-ApiError", () => {
    render(<ErrorState error={new Error("boom")} />);
    expect(screen.getByRole("alert").textContent).toContain(
      "Si è verificato un errore imprevisto.",
    );
  });

  it("shows a retry button only when onRetry is given, and calls it on click", () => {
    const onRetry = vi.fn();
    const { rerender } = render(<ErrorState error={new ApiError(500, "x")} />);
    expect(screen.queryByRole("button")).toBeNull();
    rerender(<ErrorState error={new ApiError(500, "x")} onRetry={onRetry} />);
    screen.getByRole("button", { name: "Riprova" }).click();
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});

describe("StatusBadge", () => {
  it("carries a glyph and a text label, never color alone", () => {
    render(<StatusBadge severity="critical" label="non risponde" />);
    const badge = screen.getByText("non risponde");
    expect(badge.className).toContain("status-badge--critical");
    expect(badge.querySelector(".status-badge__glyph")).toBeTruthy();
  });
});
