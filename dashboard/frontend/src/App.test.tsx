import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { App } from "./App";

afterEach(cleanup);

describe("App", () => {
  it("mostra il titolo e l'avviso sui dati di prova in italiano", () => {
    render(<App />);
    expect(screen.getByRole("heading", { level: 1, name: "Home DNS" })).toBeTruthy();
    expect(screen.getByText(/dati di prova/)).toBeTruthy();
  });
});
