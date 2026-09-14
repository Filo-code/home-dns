import { useApiClient } from "../api/useApiClient";
import type { ConfigView, OverviewResponse } from "../api/types";
import { BarGauge } from "../components/charts/BarGauge";
import { Card, StatRow } from "../components/Card";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { usePolling } from "../hooks/usePolling";
import { formatBytes, formatDateTime, formatPercent, formatUptime } from "../lib/format";

const POLL_MS = 60_000;

function severityForPercent(value: number): "ok" | "warning" | "critical" {
  if (value >= 90) return "critical";
  if (value >= 70) return "warning";
  return "ok";
}

export function System() {
  const { get } = useApiClient();
  const overview = usePolling<OverviewResponse>(
    () => get<OverviewResponse>("/api/v1/overview"),
    POLL_MS,
  );
  const config = usePolling<ConfigView>(() => get<ConfigView>("/api/v1/config"), 300_000);

  if (overview.loading && !overview.data) return <LoadingState />;
  if (overview.error && !overview.data) {
    return <ErrorState error={overview.error} onRetry={overview.refresh} />;
  }
  if (!overview.data) return null;
  const system = overview.data.system;
  const ramPercent = system
    ? Math.round((system.memory_used_bytes / system.memory_total_bytes) * 1000) / 10
    : 0;

  return (
    <div className="page page--system">
      <h1>Sistema</h1>

      <Card title="Risorse">
        {system ? (
          <>
            <BarGauge
              value={system.cpu_percent}
              label={`CPU: ${formatPercent(system.cpu_percent)}`}
              severity={severityForPercent(system.cpu_percent)}
            />
            <BarGauge
              value={ramPercent}
              label={`RAM: ${formatBytes(system.memory_used_bytes)} / ${formatBytes(system.memory_total_bytes)}`}
              severity={severityForPercent(ramPercent)}
            />
            <StatRow
              label="Temperatura"
              value={
                system.temperature_celsius != null
                  ? `${system.temperature_celsius.toFixed(1)} °C`
                  : "—"
              }
            />
            <StatRow label="Uptime" value={formatUptime(system.uptime_seconds)} />
            <StatRow label="Carico (1 min)" value={system.load_1m.toFixed(2)} />
          </>
        ) : (
          <p>Dati di sistema non disponibili: il provider DNS non risponde al momento.</p>
        )}
      </Card>

      <Card title="Manutenzione">
        <StatRow
          label="Ultimo backup"
          value={
            overview.data.last_backup_at ? formatDateTime(overview.data.last_backup_at) : "—"
          }
        />
        <StatRow
          label="Ultimo aggiornamento liste"
          value={
            overview.data.last_blocklist_update_at
              ? formatDateTime(overview.data.last_blocklist_update_at)
              : "—"
          }
        />
        <StatRow label="Incidenti aperti" value={overview.data.open_incidents} />
      </Card>

      {config.data && (
        <>
          <Card title="Soglie di archiviazione">
            <StatRow
              label="Sano sotto"
              value={formatPercent(config.data.storage.thresholds_percent.healthy_below)}
            />
            <StatRow
              label="Avviso da"
              value={formatPercent(config.data.storage.thresholds_percent.warning_from)}
            />
            <StatRow
              label="Pulizia automatica da"
              value={formatPercent(config.data.storage.thresholds_percent.auto_cleanup_from)}
            />
            <StatRow
              label="Emergenza da"
              value={formatPercent(config.data.storage.thresholds_percent.emergency_from)}
            />
          </Card>

          <Card title="Conservazione dati">
            <StatRow
              label="Backup conservati"
              value={config.data.storage.retention.backups_keep}
            />
            <StatRow
              label="Cronologia query"
              value={`${config.data.storage.retention.query_history_days} giorni`}
            />
          </Card>

          <Card title="Raccolta metriche">
            <StatRow
              label="Intervallo campionamento"
              value={`${config.data.metrics.poll_interval_seconds} s`}
            />
            <StatRow
              label="Intervallo scrittura"
              value={`${config.data.metrics.flush_interval_seconds} s`}
            />
            <StatRow label="Fuso orario" value={config.data.metrics.timezone} />
          </Card>
        </>
      )}
    </div>
  );
}
