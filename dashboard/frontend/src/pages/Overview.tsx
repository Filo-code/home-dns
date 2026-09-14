import { useEffect, useState } from "react";

import { useApiClient } from "../api/useApiClient";
import type { HistoryResponse, OverviewResponse } from "../api/types";
import { Card, StatRow } from "../components/Card";
import { LineChart } from "../components/charts/LineChart";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { StatusBadge } from "../components/StatusBadge";
import { usePolling } from "../hooks/usePolling";
import {
  formatBytes,
  formatDateTime,
  formatLatency,
  formatNumber,
  formatPercent,
  formatTime,
  formatUptime,
} from "../lib/format";
import { healthLabelIt, severityFromHealth } from "../lib/severity";
import { alertsPath, Link } from "../router";

const POLL_MS = 60_000;

export function Overview() {
  const { get } = useApiClient();
  const { data, error, loading, refresh } = usePolling<OverviewResponse>(
    () => get<OverviewResponse>("/api/v1/overview"),
    POLL_MS,
  );
  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [historyError, setHistoryError] = useState<unknown>(null);

  useEffect(() => {
    // On page load only — not continuously (docs/specs/a8-frontend-dashboard.md §13).
    get<HistoryResponse>("/api/v1/metrics/history", { query: { resolution: "hour" } })
      .then(setHistory)
      .catch(setHistoryError);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading && !data) return <LoadingState />;
  if (error && !data) return <ErrorState error={error} onRetry={refresh} />;
  if (!data) return null;

  const providerSeverity = severityFromHealth(data.provider.status);
  const cacheHitPercent =
    data.last_24h.cache_hit_ratio !== null ? data.last_24h.cache_hit_ratio * 100 : null;

  return (
    <div className="page page--overview">
      <h1>Panoramica</h1>
      <p className="page__updated-at">
        {data.metrics_as_of
          ? `Aggiornato alle ${formatTime(data.metrics_as_of)}`
          : "In attesa dei primi dati aggregati"}
      </p>

      <div className="card-grid">
        <Card title="Stato DNS">
          <StatusBadge
            severity={providerSeverity}
            label={`Servizio DNS: ${healthLabelIt(data.provider.status)}`}
          />
          <StatRow label="Query al secondo" value={formatNumber(data.queries_per_second)} />
        </Card>

        <Card title="Query (24h)">
          <StatRow label="Totali" value={formatNumber(data.last_24h.total)} />
          <StatRow label="Bloccate" value={formatNumber(data.last_24h.blocked)} />
          <StatRow label="Consentite" value={formatNumber(data.last_24h.allowed)} />
          <StatRow label="% bloccate" value={formatPercent(data.last_24h.block_percentage)} />
          <StatRow
            label="Cache hit"
            value={cacheHitPercent !== null ? formatPercent(cacheHitPercent) : "—"}
          />
          <StatRow label="Latenza p50" value={formatLatency(data.last_24h.latency_p50_ms)} />
          <StatRow label="Latenza p95" value={formatLatency(data.last_24h.latency_p95_ms)} />
        </Card>

        <Card title="Sistema">
          {data.system ? (
            <>
              <StatRow label="CPU" value={formatPercent(data.system.cpu_percent)} />
              <StatRow
                label="RAM"
                value={`${formatBytes(data.system.memory_used_bytes)} / ${formatBytes(data.system.memory_total_bytes)}`}
              />
              <StatRow
                label="Temperatura"
                value={
                  data.system.temperature_celsius != null
                    ? `${data.system.temperature_celsius.toFixed(1)} °C`
                    : "—"
                }
              />
              <StatRow label="Uptime" value={formatUptime(data.system.uptime_seconds)} />
            </>
          ) : (
            <p>Dati di sistema non disponibili: il provider DNS non risponde al momento.</p>
          )}
        </Card>

        <Card title="Manutenzione">
          <StatRow
            label="Incidenti aperti"
            value={<Link to={alertsPath()}>{formatNumber(data.open_incidents)}</Link>}
          />
          <StatRow
            label="Ultimo backup"
            value={data.last_backup_at ? formatDateTime(data.last_backup_at) : "—"}
          />
          <StatRow
            label="Ultimo aggiornamento liste"
            value={
              data.last_blocklist_update_at ? formatDateTime(data.last_blocklist_update_at) : "—"
            }
          />
        </Card>
      </div>

      <Card title="Query nelle ultime 24 ore" className="card--wide">
        {historyError ? (
          <ErrorState error={historyError} />
        ) : history ? (
          <LineChart
            points={history.points.map((point) => ({
              x: formatTime(point.bucket_start),
              y: point.counters.total,
            }))}
            formatValue={formatNumber}
          />
        ) : (
          <LoadingState />
        )}
      </Card>
    </div>
  );
}
