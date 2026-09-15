import { render, waitFor, type RenderResult } from "@testing-library/react";
import type { ReactNode } from "react";
import { expect } from "vitest";

import type { Role } from "../api/types";
import { AuthProvider, useAuth } from "../context/AuthContext";
import { OverviewProvider } from "../context/OverviewContext";
import { installMockFetch, jsonResponse, type MockResponse } from "./mockFetch";

/** Mirrors App.tsx's AppShell gating: a page never mounts before auth is settled — so its
 * effects can never race AuthProvider's own boot fetch for the mock queue, exactly as in the
 * real app. Without this, a page rendered directly under AuthProvider mounts on the very same
 * commit as the provider (React fires a child's effects before its parent's), so the page's own
 * fetches can fire before the boot session fetch and consume the wrong queued response. */
function Gate({ children }: { children: ReactNode }) {
  const { state } = useAuth();
  if (state.status !== "authenticated") return null;
  return <>{children}</>;
}

export async function renderAuthenticatedPage(
  ui: ReactNode,
  options: {
    role?: Role;
    username?: string;
    responses?: MockResponse[];
    /** Wraps `ui` in OverviewProvider, mirroring App.tsx's real shell — only pages that call
     * useOverview() (currently just Overview) need this; everything else stays unaffected. */
    withOverview?: boolean;
  } = {},
): Promise<RenderResult & { calls: { url: string; init?: RequestInit }[] }> {
  const { role = "admin", username = "anna", responses = [], withOverview = false } = options;
  const { calls } = installMockFetch([
    jsonResponse(200, { username, role, csrf_token: "csrf-test-token" }),
    ...responses,
  ]);
  const rendered = render(
    <AuthProvider>
      <Gate>{withOverview ? <OverviewProvider>{ui}</OverviewProvider> : ui}</Gate>
    </AuthProvider>,
  );
  await waitFor(() => expect(rendered.container.innerHTML).not.toBe(""));
  return { ...rendered, calls };
}
