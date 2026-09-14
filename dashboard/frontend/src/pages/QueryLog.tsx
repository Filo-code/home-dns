/**
 * Admin-only. Results live only in React state for this page's lifetime — never written to
 * localStorage/sessionStorage (docs/specs/a8-frontend-dashboard.md §12).
 */
import { useEffect, useState, type FormEvent } from "react";

import { useApiClient } from "../api/useApiClient";
import type { QueryLogEntry, QueryOutcome, QueryPage, QueriesQuery } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { Table, type Column } from "../components/Table";
import { formatDateTime, formatLatency } from "../lib/format";

const OUTCOMES: { value: QueryOutcome | ""; label: string }[] = [
  { value: "", label: "Tutti" },
  { value: "forwarded", label: "Inoltrate" },
  { value: "cached", label: "Dalla cache" },
  { value: "blocked", label: "Bloccate" },
  { value: "other", label: "Altro" },
];

const columns: Column<QueryLogEntry>[] = [
  { key: "time", header: "Ora", render: (row) => formatDateTime(row.time) },
  { key: "client", header: "Client", render: (row) => row.client_address },
  { key: "domain", header: "Dominio", render: (row) => row.domain },
  { key: "type", header: "Tipo", render: (row) => row.query_type },
  { key: "outcome", header: "Esito", render: (row) => row.outcome },
  { key: "blocked_by", header: "Bloccato da", render: (row) => row.blocked_by ?? "—" },
  { key: "latency", header: "Latenza", render: (row) => formatLatency(row.latency_ms) },
];

export function QueryLog() {
  const { get } = useApiClient();
  const [domain, setDomain] = useState("");
  const [client, setClient] = useState("");
  const [outcome, setOutcome] = useState<QueryOutcome | "">("");
  const [hours, setHours] = useState(1);
  const [entries, setEntries] = useState<QueryLogEntry[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function runQuery(cursor?: string) {
    setLoading(true);
    setError(null);
    try {
      const until = new Date();
      const since = new Date(until.getTime() - hours * 3_600_000);
      const query: QueriesQuery = {
        since: since.toISOString(),
        until: until.toISOString(),
        domain: domain.trim() || undefined,
        client: client.trim() || undefined,
        outcome: outcome || undefined,
        limit: 100,
        cursor,
      };
      const result = await get<QueryPage>("/api/v1/queries", { query });
      setEntries((previous) => (cursor ? [...previous, ...result.entries] : result.entries));
      setNextCursor(result.next_cursor ?? null);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void runQuery();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setEntries([]);
    setNextCursor(null);
    void runQuery();
  }

  return (
    <div className="page page--query-log">
      <h1>Registro query</h1>

      <form className="filter-form" onSubmit={handleSubmit}>
        <label htmlFor="domain-filter">Dominio</label>
        <input
          id="domain-filter"
          value={domain}
          onChange={(event) => setDomain(event.target.value)}
          placeholder="esempio.example"
        />

        <label htmlFor="client-filter">Client (IP)</label>
        <input
          id="client-filter"
          value={client}
          onChange={(event) => setClient(event.target.value)}
          placeholder="192.0.2.10"
        />

        <label htmlFor="outcome-filter">Esito</label>
        <select
          id="outcome-filter"
          value={outcome}
          onChange={(event) => setOutcome(event.target.value as QueryOutcome | "")}
        >
          {OUTCOMES.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>

        <label htmlFor="hours-filter">Periodo</label>
        <select
          id="hours-filter"
          value={hours}
          onChange={(event) => setHours(Number(event.target.value))}
        >
          <option value={1}>Ultima ora</option>
          <option value={6}>Ultime 6 ore</option>
          <option value={24}>Ultime 24 ore</option>
        </select>

        <button type="submit" className="button button--primary" disabled={loading}>
          Filtra
        </button>
      </form>

      {error != null && <ErrorState error={error} onRetry={() => void runQuery()} />}

      {entries.length === 0 && !loading && !error ? (
        <EmptyState />
      ) : (
        <Table columns={columns} rows={entries} rowKey={(row) => row.id} caption="Query DNS" />
      )}

      {loading && <LoadingState />}

      {nextCursor && !loading && (
        <button
          type="button"
          className="button button--secondary"
          onClick={() => void runQuery(nextCursor)}
        >
          Carica altri
        </button>
      )}
    </div>
  );
}
