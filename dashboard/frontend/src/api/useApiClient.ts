/**
 * The stateful policy layer over apiFetch (docs/specs/a8-frontend-dashboard.md §8):
 *  - any 401           -> clear AuthContext, redirect to /login preserving the current path
 *  - a mutation's 403 that is specifically a stale/missing CSRF token
 *                       -> refresh the session once (gets a fresh token), retry the mutation
 *                          once, then give up (never an infinite loop)
 *  - a 403 for role/permission (not CSRF)  -> returned to the caller as-is; pages render their
 *                          own "Non hai i permessi..." state, this hook does not redirect for it
 */
import { useCallback } from "react";

import { useAuth } from "../context/AuthContext";
import { loginPath, navigate } from "../router";
import { ApiError, apiFetch, type ApiFetchOptions } from "./client";
import type { SessionView } from "./types";

export interface ApiClient {
  get: <T>(
    path: string,
    options?: Omit<ApiFetchOptions, "method" | "body" | "csrfToken">,
  ) => Promise<T>;
  mutate: <T>(
    path: string,
    method: "POST" | "PUT" | "PATCH" | "DELETE",
    body?: unknown,
  ) => Promise<T>;
}

export function useApiClient(): ApiClient {
  const { state, setAnonymous, setCsrfToken } = useAuth();

  const handleUnauthenticated = useCallback(() => {
    setAnonymous();
    const current = window.location.pathname + window.location.search;
    navigate(loginPath(current), { replace: true });
  }, [setAnonymous]);

  const get = useCallback(
    async <T,>(
      path: string,
      options: Omit<ApiFetchOptions, "method" | "body" | "csrfToken"> = {},
    ): Promise<T> => {
      try {
        return await apiFetch<T>(path, options);
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) handleUnauthenticated();
        throw error;
      }
    },
    [handleUnauthenticated],
  );

  const mutate = useCallback(
    async <T,>(
      path: string,
      method: "POST" | "PUT" | "PATCH" | "DELETE",
      body?: unknown,
    ): Promise<T> => {
      try {
        return await apiFetch<T>(path, { method, body, csrfToken: state.csrfToken ?? undefined });
      } catch (error) {
        if (!(error instanceof ApiError)) throw error;
        if (error.status === 401) {
          handleUnauthenticated();
          throw error;
        }
        if (error.isCsrfFailure) {
          // One refresh, one retry — never more than this single extra attempt.
          const session = await apiFetch<SessionView>("/api/v1/auth/session").catch(() => null);
          if (session === null) {
            handleUnauthenticated();
            throw error;
          }
          setCsrfToken(session.csrf_token);
          return await apiFetch<T>(path, { method, body, csrfToken: session.csrf_token });
        }
        throw error;
      }
    },
    [state.csrfToken, handleUnauthenticated, setCsrfToken],
  );

  return { get, mutate };
}
