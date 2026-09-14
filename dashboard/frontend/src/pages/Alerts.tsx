/** A5 owns monitoring state; this page only presents it (docs/specs/a8-frontend-dashboard.md
 * §6) — no severity or incident logic is computed here beyond a display mapping. */
import { useApiClient } from "../api/useApiClient";
import type { IncidentView } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { StatusBadge } from "../components/StatusBadge";
import { Table, type Column } from "../components/Table";
import { usePolling } from "../hooks/usePolling";
import { formatDateTime } from "../lib/format";
import { incidentLabelIt, severityFromIncident } from "../lib/severity";

const POLL_MS = 120_000;

const columns: Column<IncidentView>[] = [
  {
    key: "state",
    header: "Stato",
    render: (incident) => (
      <StatusBadge
        severity={severityFromIncident(incident.state)}
        label={incidentLabelIt(incident.state)}
      />
    ),
  },
  { key: "check_name", header: "Controllo", render: (incident) => incident.check_name },
  {
    key: "opened_at",
    header: "Aperto il",
    render: (incident) => (incident.opened_at ? formatDateTime(incident.opened_at) : "—"),
  },
  {
    key: "last_change_at",
    header: "Ultimo cambiamento",
    render: (incident) =>
      incident.last_change_at ? formatDateTime(incident.last_change_at) : "—",
  },
];

export function Alerts() {
  const { get } = useApiClient();
  const { data, error, loading, refresh } = usePolling<IncidentView[]>(
    () => get<IncidentView[]>("/api/v1/alerts"),
    POLL_MS,
  );

  if (loading && !data) return <LoadingState />;
  if (error && !data) return <ErrorState error={error} onRetry={refresh} />;
  if (!data) return null;

  return (
    <div className="page page--alerts">
      <h1>Avvisi</h1>
      {data.length === 0 ? (
        <EmptyState label="Nessun incidente attivo." />
      ) : (
        <Table
          columns={columns}
          rows={data}
          rowKey={(incident) => incident.check_name}
          caption="Incidenti"
        />
      )}
    </div>
  );
}
