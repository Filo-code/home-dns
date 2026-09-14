/**
 * Session state: React Context + useReducer, nothing heavier (docs/specs/a8-frontend-
 * dashboard.md §5, §8). Holds only {status, username, role, csrfToken} — never the session
 * cookie (HttpOnly, the server never lets JS see it) and never persisted to localStorage/
 * sessionStorage: a full reload always re-derives this from GET /api/v1/auth/session, which is
 * safe because the cookie, not this state, is what the server actually trusts.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  type ReactNode,
} from "react";

import { ApiError, apiFetch } from "../api/client";
import type { Role, SessionView } from "../api/types";

export type AuthStatus = "loading" | "authenticated" | "anonymous";

export interface AuthState {
  status: AuthStatus;
  username: string | null;
  role: Role | null;
  csrfToken: string | null;
}

type AuthAction =
  | { type: "authenticated"; session: SessionView }
  | { type: "anonymous" }
  | { type: "csrf-refreshed"; csrfToken: string };

const initialState: AuthState = {
  status: "loading",
  username: null,
  role: null,
  csrfToken: null,
};

function reducer(state: AuthState, action: AuthAction): AuthState {
  switch (action.type) {
    case "authenticated":
      return {
        status: "authenticated",
        username: action.session.username,
        role: action.session.role,
        csrfToken: action.session.csrf_token,
      };
    case "anonymous":
      return { status: "anonymous", username: null, role: null, csrfToken: null };
    case "csrf-refreshed":
      return { ...state, csrfToken: action.csrfToken };
  }
}

interface AuthContextValue {
  state: AuthState;
  /** Re-fetches GET /auth/session; used on boot and after login/logout. */
  refresh: () => Promise<AuthState>;
  setAuthenticated: (session: SessionView) => void;
  setAnonymous: () => void;
  setCsrfToken: (token: string) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  const refresh = useCallback(async (): Promise<AuthState> => {
    try {
      const session = await apiFetch<SessionView>("/api/v1/auth/session");
      dispatch({ type: "authenticated", session });
      return {
        status: "authenticated",
        username: session.username,
        role: session.role,
        csrfToken: session.csrf_token,
      };
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        dispatch({ type: "anonymous" });
        return { status: "anonymous", username: null, role: null, csrfToken: null };
      }
      throw error;
    }
  }, []);

  useEffect(() => {
    // Any boot failure (401, or the backend being unreachable) lands on the login page rather
    // than leaving the app stuck on "loading" forever; a truly-down backend then surfaces
    // "Impossibile contattare il server" from the login attempt itself.
    refresh().catch(() => dispatch({ type: "anonymous" }));
  }, [refresh]);

  const value = useMemo<AuthContextValue>(
    () => ({
      state,
      refresh,
      setAuthenticated: (session: SessionView) => dispatch({ type: "authenticated", session }),
      setAnonymous: () => dispatch({ type: "anonymous" }),
      setCsrfToken: (token: string) => dispatch({ type: "csrf-refreshed", csrfToken: token }),
    }),
    [state, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used within an AuthProvider");
  return value;
}
