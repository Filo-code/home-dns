/**
 * A small hand-written SPA router (no react-router — see docs/specs/a8-frontend-dashboard.md
 * §5): the app has a fixed, known set of routes, none nested, none needing data loaders.
 *
 * `navigate()` is a plain function, usable outside React (e.g. from the API client's 401
 * handler) as well as from <Link>. Route state itself is plain module state with a tiny
 * subscriber list; `useRoute()` is the only React binding.
 */
import { createElement, type AnchorHTMLAttributes, type MouseEvent, type ReactNode } from "react";
import { useSyncExternalStore } from "react";

export type RouteName =
  | "overview"
  | "devices"
  | "device-detail"
  | "security"
  | "system"
  | "alerts"
  | "queries"
  | "login"
  | "not-found";

export interface Route {
  name: RouteName;
  params: Record<string, string>;
}

interface RouteDefinition {
  name: RouteName;
  /** Path segments; a segment starting with ":" captures into params. */
  pattern: string[];
}

const ROUTES: RouteDefinition[] = [
  { name: "overview", pattern: [] },
  { name: "devices", pattern: ["devices"] },
  { name: "device-detail", pattern: ["devices", ":id"] },
  { name: "security", pattern: ["security"] },
  { name: "system", pattern: ["system"] },
  { name: "alerts", pattern: ["alerts"] },
  { name: "queries", pattern: ["queries"] },
  { name: "login", pattern: ["login"] },
];

function segmentsOf(pathname: string): string[] {
  return pathname.split("/").filter((segment) => segment.length > 0);
}

function match(pathname: string): Route {
  const segments = segmentsOf(pathname);
  for (const route of ROUTES) {
    if (route.pattern.length !== segments.length) continue;
    const params: Record<string, string> = {};
    let matched = true;
    for (let i = 0; i < route.pattern.length; i++) {
      const part = route.pattern[i]!;
      const segment = segments[i]!;
      if (part.startsWith(":")) {
        params[part.slice(1)] = decodeURIComponent(segment);
      } else if (part !== segment) {
        matched = false;
        break;
      }
    }
    if (matched) return { name: route.name, params };
  }
  return { name: "not-found", params: {} };
}

const listeners = new Set<() => void>();

function getSnapshot(): string {
  return window.location.pathname;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("popstate", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("popstate", listener);
  };
}

/** Navigate without a full page reload. Safe to call from outside React (module-level code). */
export function navigate(path: string, options: { replace?: boolean } = {}): void {
  if (options.replace) {
    window.history.replaceState(null, "", path);
  } else {
    window.history.pushState(null, "", path);
  }
  for (const listener of listeners) listener();
}

/** The current route, reactive — re-renders the calling component on navigation. */
export function useRoute(): Route {
  const pathname = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  return match(pathname);
}

export function overviewPath(): string {
  return "/";
}
export function devicesPath(): string {
  return "/devices";
}
export function deviceDetailPath(id: number | string): string {
  return `/devices/${id}`;
}
export function securityPath(): string {
  return "/security";
}
export function systemPath(): string {
  return "/system";
}
export function alertsPath(): string {
  return "/alerts";
}
export function queriesPath(): string {
  return "/queries";
}
export function loginPath(next?: string): string {
  return next ? `/login?next=${encodeURIComponent(next)}` : "/login";
}

/** The `next` query parameter set by `loginPath()`, if present and safe to use. */
export function intendedPath(): string {
  const next = new URLSearchParams(window.location.search).get("next");
  if (next && next.startsWith("/") && !next.startsWith("//")) return next;
  return overviewPath();
}

interface LinkProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  to: string;
  children?: ReactNode;
}

/** A same-tab, no-reload link. Renders a real <a> so middle-click/open-in-new-tab still work. */
export function Link({ to, onClick, children, ...rest }: LinkProps) {
  return createElement(
    "a",
    {
      ...rest,
      href: to,
      onClick: (event: MouseEvent<HTMLAnchorElement>) => {
        onClick?.(event);
        if (
          event.defaultPrevented ||
          event.button !== 0 ||
          event.metaKey ||
          event.ctrlKey ||
          event.shiftKey ||
          event.altKey
        ) {
          return;
        }
        event.preventDefault();
        navigate(to);
      },
    },
    children,
  );
}
