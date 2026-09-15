import { useApiClient } from "../api/useApiClient";
import type {
  AnomalyView,
  BlocklistSourceView,
  ConfigView,
  IncidentView,
  OverviewResponse,
} from "../api/types";
import { AnomalyList } from "../components/AnomalyList";
import { Card, StatRow } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { StatusBadge } from "../components/StatusBadge";
import { Table, type Column } from "../components/Table";
import { usePolling } from "../hooks/usePolling";
import { formatDateTime, formatNumber, formatRelative } from "../lib/format";
import { incidentLabelIt, severityFromIncident } from "../lib/severity";

const POLL_MS = 120_000;

export function Security() {
  const { get } = useApiClient();
  const config = usePolling<ConfigView>(() => get<ConfigView>("/api/v1/config"), POLL_MS);
  const overview = usePolling<OverviewResponse>(
    () => get<OverviewResponse>("/api/v1/overview"),
    POLL_MS,
  );
  const alerts = usePolling<IncidentView[]>(() => get<IncidentView[]>("/api/v1/alerts"), POLL_MS);
  const anomalies = usePolling<AnomalyView[]>(
    () => get<AnomalyView[]>("/api/v1/anomalies"),
    POLL_MS,
  );

  if ((config.loading && !config.data) || (overview.loading && !overview.data)) {
    return <LoadingState />;
  }
  if (config.error && !config.data) {
    return <ErrorState error={config.error} onRetry={config.refresh} />;
  }
  if (overview.error && !overview.data) {
    return <ErrorState error={overview.error} onRetry={overview.refresh} />;
  }
  if (!config.data || !overview.data) return null;

  const blockedBySource = overview.data.last_24h.blocked_by_source;

  // Blocked counts come from A7 per blocklist SOURCE, never fabricated per category — a source
  // like Multi PRO covers several categories at once with no per-domain category attribution
  // (docs/specs/a7-backend.md §5). Categories are shown alongside each source, not summed.
  const sourceColumns: Column<BlocklistSourceView>[] = [
    { key: "name", header: "Lista", render: (source) => source.name },
    { key: "categories", header: "Categorie", render: (source) => source.categories.join(", ") },
    {
      key: "interval",
      header: "Intervallo aggiornamento",
      render: (source) => `${source.update_interval_hours} h`,
    },
    {
      key: "blocked",
      header: "Bloccate (24h)",
      render: (source) => formatNumber(blockedBySource[source.id] ?? 0),
    },
    {
      key: "freshness",
      header: "Ultimo aggiornamento",
      render: (source) => formatRelative(source.last_activated_at),
    },
  ];

  const alertColumns: Column<IncidentView>[] = [
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

  return (
    <div className="page page--security">
      <h1>Sicurezza</h1>

      <Card title="Liste di blocco">
        {config.data.blocklist_sources.length === 0 ? (
          <EmptyState />
        ) : (
          <Table
            columns={sourceColumns}
            rows={config.data.blocklist_sources}
            rowKey={(source) => source.id}
            caption="Liste di blocco"
          />
        )}
      </Card>

      <Card title="Aggiornamento liste">
        <StatRow
          label="Ultimo aggiornamento"
          value={
            overview.data.last_blocklist_update_at
              ? formatDateTime(overview.data.last_blocklist_update_at)
              : "—"
          }
        />
      </Card>

      <Card title="Incidenti di sicurezza" className="card--wide">
        {alerts.loading && !alerts.data ? (
          <LoadingState />
        ) : alerts.error && !alerts.data ? (
          <ErrorState error={alerts.error} onRetry={alerts.refresh} />
        ) : !alerts.data || alerts.data.length === 0 ? (
          <EmptyState label="Nessun incidente attivo." />
        ) : (
          <Table
            columns={alertColumns}
            rows={alerts.data}
            rowKey={(incident) => incident.check_name}
            caption="Incidenti di sicurezza"
          />
        )}
      </Card>

      <Card title="Anomalie DNS (rilevamento passivo)" className="card--wide">
        {anomalies.loading && !anomalies.data ? (
          <LoadingState />
        ) : anomalies.error && !anomalies.data ? (
          <ErrorState error={anomalies.error} onRetry={anomalies.refresh} />
        ) : !anomalies.data ? null : (
          <AnomalyList anomalies={anomalies.data} limit={20} />
        )}
      </Card>
    </div>
  );
}
