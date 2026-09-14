/**
 * A small typed apiFetch<T>() — no Axios, no other HTTP client (docs/specs/a8-frontend-
 * dashboard.md §5). Always same-origin relative paths (`/api/v1/...`); the browser must never
 * call Pi-hole directly, only this. Stateless and auth-context-agnostic: it throws a typed
 * ApiError for the caller to react to. The stateful policy (401 -> clear session and redirect,
 * 403-from-stale-CSRF -> refresh and retry once) lives one layer up, in useApiClient.ts, which
 * has access to AuthContext — keeping this module framework-free and easy to unit test.
 */

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const CSRF_HEADER = "X-CSRF-Token";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }

  /** The 403 raised specifically for a missing/stale CSRF token (auth.py `current_session`),
   * distinct from a 403 for lacking the admin role — see useApiClient's retry-once logic. */
  get isCsrfFailure(): boolean {
    return this.status === 403 && this.detail.toLowerCase().includes("csrf");
  }
}

export interface ApiFetchOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  csrfToken?: string;
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: ApiFetchOptions["query"]): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null) params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

async function readDetail(response: Response): Promise<string> {
  try {
    const data: unknown = await response.clone().json();
    if (data && typeof data === "object" && "detail" in data) {
      const detail = (data as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
    }
  } catch {
    // not JSON, or empty body — fall through to a generic message below
  }
  return response.statusText || `HTTP ${response.status}`;
}

/**
 * Same-origin fetch with JSON handling, typed errors and CSRF on unsafe methods. `credentials`
 * is explicit even though 'same-origin' is already fetch's default, to document the intent
 * (docs/specs/a8-frontend-dashboard.md §9: same-origin always, in dev via the Vite proxy too).
 */
export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (UNSAFE_METHODS.has(method) && options.csrfToken) headers[CSRF_HEADER] = options.csrfToken;

  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.query), {
      method,
      headers,
      credentials: "same-origin",
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: options.signal,
    });
  } catch {
    // Network failure / backend unreachable — never leak the raw error object to the UI.
    throw new ApiError(0, "Impossibile contattare il server.");
  }

  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
