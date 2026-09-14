import { useState, type FormEvent } from "react";

import { ApiError, apiFetch } from "../api/client";
import type { SessionView } from "../api/types";
import { useAuth } from "../context/AuthContext";
import { intendedPath, navigate } from "../router";

/** Never distinguishes "unknown username" from "wrong password" (auth.py does the same
 * server-side, at matched timing) — see docs/specs/a8-frontend-dashboard.md §8, §11. */
function messageFor(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "Credenziali non valide.";
    if (error.status === 429) return "Troppi tentativi, riprova tra qualche minuto.";
  }
  return "Impossibile contattare il server.";
}

export function Login() {
  const { setAuthenticated } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const session = await apiFetch<SessionView>("/api/v1/auth/login", {
        method: "POST",
        body: { username, password },
      });
      setAuthenticated(session);
      navigate(intendedPath(), { replace: true });
    } catch (err) {
      setError(messageFor(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-page">
      <form className="login-form" onSubmit={(event) => void handleSubmit(event)}>
        <h1>Home DNS</h1>
        <p className="login-form__subtitle">Accedi alla dashboard</p>
        <label htmlFor="username">Nome utente</label>
        <input
          id="username"
          name="username"
          autoComplete="username"
          required
          value={username}
          onChange={(event) => setUsername(event.target.value)}
        />
        <label htmlFor="password">Password</label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        {error && (
          <p className="login-form__error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" className="button button--primary" disabled={submitting}>
          {submitting ? "Accesso in corso…" : "Accedi"}
        </button>
      </form>
    </main>
  );
}
