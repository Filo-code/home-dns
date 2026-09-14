/**
 * The one place that turns a caught error into user-facing Italian copy — never a raw
 * exception string (docs/specs/a8-frontend-dashboard.md §15). 401 is handled globally by
 * useApiClient (redirect to /login) before a page ever renders this for it; the cases here are
 * what a page can still legitimately see.
 */
import { ApiError } from "../api/client";

function messageFor(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.status) {
      case 403:
        return "Non hai i permessi per questa sezione.";
      case 404:
        return "Risorsa non trovata.";
      case 429:
        return "Troppi tentativi, riprova tra qualche minuto.";
      case 503:
        return "Il servizio DNS non risponde al momento.";
      case 0:
        return "Impossibile contattare il server.";
      default:
        return "Si è verificato un errore imprevisto.";
    }
  }
  return "Si è verificato un errore imprevisto.";
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="state state--error" role="alert">
      <p>{messageFor(error)}</p>
      {onRetry && (
        <button type="button" className="button button--secondary" onClick={onRetry}>
          Riprova
        </button>
      )}
    </div>
  );
}
