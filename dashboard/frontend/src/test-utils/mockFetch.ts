import { vi } from "vitest";

/** A minimal queued-response fetch stub — no new HTTP-mocking dependency. */
export interface MockResponse {
  status: number;
  body?: unknown;
  statusText?: string;
}

export function installMockFetch(responses: MockResponse[]): {
  calls: { url: string; init?: RequestInit }[];
} {
  const calls: { url: string; init?: RequestInit }[] = [];
  const queue = [...responses];

  const fetchMock = vi.fn(async (url: string | URL, init?: RequestInit) => {
    calls.push({ url: String(url), init });
    const next = queue.shift();
    if (!next) {
      throw new Error(`mock fetch: no queued response for ${String(url)}`);
    }
    // A Response with a 204/205/304 status must have a null body, not "" (Fetch spec).
    const body = next.body === undefined ? null : JSON.stringify(next.body);
    return new Response(body, {
      status: next.status,
      statusText: next.statusText,
      headers: next.body !== undefined ? { "Content-Type": "application/json" } : undefined,
    });
  });

  vi.stubGlobal("fetch", fetchMock);
  return { calls };
}

export function jsonResponse(status: number, body: unknown): MockResponse {
  return { status, body };
}
