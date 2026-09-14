import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Link, deviceDetailPath, intendedPath, loginPath, navigate, useRoute } from "./router";

afterEach(() => {
  cleanup();
  window.history.pushState(null, "", "/");
});

function RouteProbe() {
  const route = useRoute();
  return (
    <span data-testid="route">
      {route.name}:{JSON.stringify(route.params)}
    </span>
  );
}

describe("useRoute", () => {
  it.each([
    ["/", "overview", {}],
    ["/devices", "devices", {}],
    ["/devices/42", "device-detail", { id: "42" }],
    ["/security", "security", {}],
    ["/system", "system", {}],
    ["/alerts", "alerts", {}],
    ["/queries", "queries", {}],
    ["/login", "login", {}],
    ["/nope", "not-found", {}],
    ["/devices/42/extra", "not-found", {}],
  ])("matches %s", (path, name, params) => {
    window.history.pushState(null, "", path);
    render(<RouteProbe />);
    expect(screen.getByTestId("route").textContent).toBe(`${name}:${JSON.stringify(params)}`);
  });

  it("re-renders reactively when navigate() is called", () => {
    window.history.pushState(null, "", "/");
    render(<RouteProbe />);
    expect(screen.getByTestId("route").textContent).toBe("overview:{}");
    act(() => navigate("/devices"));
    expect(screen.getByTestId("route").textContent).toBe("devices:{}");
  });

  it("reacts to a browser back/forward popstate event, not just navigate()", () => {
    window.history.pushState(null, "", "/security");
    render(<RouteProbe />);
    expect(screen.getByTestId("route").textContent).toBe("security:{}");
    // Simulate the browser itself having moved back (the URL already changed, only the
    // popstate event still needs to fire) — jsdom's own history.back() isn't reliable here,
    // so this isolates exactly what useRoute's popstate subscription is responsible for.
    window.history.pushState(null, "", "/devices");
    act(() => {
      fireEvent.popState(window);
    });
    expect(screen.getByTestId("route").textContent).toBe("devices:{}");
  });
});

describe("Link", () => {
  it("navigates without a full page reload on a plain left click", () => {
    window.history.pushState(null, "", "/");
    render(
      <>
        <Link to="/devices">Dispositivi</Link>
        <RouteProbe />
      </>,
    );
    fireEvent.click(screen.getByText("Dispositivi"));
    expect(window.location.pathname).toBe("/devices");
    expect(screen.getByTestId("route").textContent).toBe("devices:{}");
  });

  it("does not intercept a modified click (e.g. ctrl-click to open in a new tab)", () => {
    window.history.pushState(null, "", "/");
    render(<Link to="/devices">Dispositivi</Link>);
    fireEvent.click(screen.getByText("Dispositivi"), { ctrlKey: true });
    expect(window.location.pathname).toBe("/"); // unchanged — the browser handles it instead
  });
});

describe("path helpers", () => {
  it("deviceDetailPath builds a /devices/:id path", () => {
    expect(deviceDetailPath(42)).toBe("/devices/42");
  });

  it("loginPath encodes the intended next path", () => {
    expect(loginPath("/devices/7")).toBe("/login?next=%2Fdevices%2F7");
    expect(loginPath()).toBe("/login");
  });

  it("intendedPath reads a safe ?next= back, defaulting to overview", () => {
    window.history.pushState(null, "", "/login?next=%2Fsecurity");
    expect(intendedPath()).toBe("/security");
    window.history.pushState(null, "", "/login");
    expect(intendedPath()).toBe("/");
  });

  it("intendedPath rejects an absolute/protocol-relative next (open-redirect guard)", () => {
    window.history.pushState(null, "", "/login?next=https%3A%2F%2Fevil.example");
    expect(intendedPath()).toBe("/");
    window.history.pushState(null, "", "/login?next=%2F%2Fevil.example");
    expect(intendedPath()).toBe("/");
  });
});
