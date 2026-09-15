import { useEffect, useState } from "react";

import { useApiClient } from "../api/useApiClient";
import type { DeviceView, HistoryResponse, IncidentEventView, Role } from "../api/types";
import { Card, StatRow } from "../components/Card";
import { AreaChart } from "../components/charts/AreaChart";
import { BarGauge } from "../components/charts/BarGauge";
import { HeartbeatStrip } from "../components/charts/HeartbeatStrip";
import { DevicesMostActive } from "../components/DevicesMostActive";
import { ErrorState } from "../components/ErrorState";
import { HealthLedger } from "../components/HealthLedger";
import { HealthRing } from "../components/HealthRing";
import { IncidentHistoryList } from "../components/IncidentHistoryList";
import { LoadingState } from "../components/LoadingState";
import { QuickActions, type AdminAction } from "../components/QuickActions";
import { RecentActivity } from "../components/RecentActivity";
import type { Severity } from "../components/StatusBadge";
import { useOverview } from "../context/OverviewContext";
import {
  formatBytes,
  formatDateTime,
  formatLatency,
  formatNumber,
  formatPercent,
  formatTime,
  formatUptime,
} from "../lib/format";
import { computeHealth } from "../lib/health";

function gaugeSeverity(percent: number, warnAt = 50, criticalAt = 85): Severity {
  if (percent >= criticalAt) return "critical";
  if (percent >= warnAt) return "warning";
  return "ok";
}

const HISTORY_INCIDENT_LIMIT = 200;

export function Overview({
  role,
  onRequestAdminAction,
}: {
  role: Role | null;
  onRequestAdminAction: (action: AdminAction) => void;
}) {
  const { get } = useApiClient();
  const { overview: data, config, error, loading } = useOverview();

  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [historyError, setHistoryError] = useState<unknown>(null);
  const [incidents, setIncidents] = useState<IncidentEventView[]>([]);
  const [devices, setDevices] = useState<DeviceView[]>([]);

  useEffect(() => {
    // On page load only — not continuously (docs/specs/a8-frontend-dashboard.md §13).
    get<HistoryResponse>("/api/v1/metrics/history", { query: { resolution: "hour" } })
      .then(setHistory)
      .catch(setHistoryError);
    get<IncidentEventView[]>("/api/v1/incidents/history", {
      query: { limit: HISTORY_INCIDENT_LIMIT },
    })
      .then(setIncidents)
      .catch(() => setIncidents([]));
    // Shared by the "Dispositivi più attivi" and "Attività recente" cards below — one
    // request, not fetched twice.
    get<DeviceView[]>("/api/v1/devices")
      .then(setDevices)
      .catch(() => setDevices([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading && !data) return <LoadingState />;
  if (error && !data) return <ErrorState error={error} />;
  if (!data) return null;

  const health = computeHealth(data, config);
  const cacheHitPercent =
    data.last_24h.cache_hit_ratio !== null ? data.last_24h.cache_hit_ratio * 100 : null;
  const memPercent = data.system
    ? (data.system.memory_used_bytes / data.system.memory_total_bytes) * 100
    : null;
  const thresholds = config?.storage.thresholds_percent;

  return (
    <div className="page page--overview">
      <h1>Panoramica</h1>
      <p className="page__updated-at">
        {data.metrics_as_of
          ? `Aggiornato alle ${formatTime(data.metrics_as_of)}`
          : "In attesa dei primi dati aggregati"}
      </p>

      <QuickActions role={role} onRequestAdminAction={onRequestAdminAction} />

      <div className="card-grid card-grid--health">
        <Card className="card--vitals">
          <HealthRing score={health.score} label={health.bandLabel} size="lg" />
        </Card>
        <Card title="Stato generale">
          <HealthLedger components={health.components} />
        </Card>
      </div>

      <div className="card-grid">
        <Card title="Query (24h)">
          <StatRow label="Totali" value={formatNumber(data.last_24h.total)} />
          <StatRow label="Bloccate" value={formatNumber(data.last_24h.blocked)} />
          <StatRow label="% bloccate" value={formatPercent(data.last_24h.block_percentage)} />
          <StatRow
            label="Cache hit"
            value={cacheHitPercent !== null ? formatPercent(cacheHitPercent) : "—"}
          />
          <StatRow
            label="Latenza p50 / p95"
            value={formatLatency(data.last_24h.latency_p50_ms)}
          />
          <StatRow label="Query al secondo" value={formatNumber(data.queries_per_second)} />
        </Card>

        <Card title="Manutenzione">
          <StatRow
            label="Ultimo backup"
            value={data.last_backup_at ? formatDateTime(data.last_backup_at) : "mai"}
          />
          <StatRow
            label="Ultimo aggiornamento liste"
            value={
              data.last_blocklist_update_at ? formatDateTime(data.last_blocklist_update_at) : "mai"
            }
          />
        </Card>
      </div>

      <Card title="Query nelle ultime 24 ore" className="card--wide">
        {historyError ? (
          <ErrorState error={historyError} />
        ) : history ? (
          <AreaChart
            points={history.points.map((point) => ({
              x: formatTime(point.bucket_start),
              allowed: point.counters.allowed,
              blocked: point.counters.blocked,
            }))}
          />
        ) : (
          <LoadingState />
        )}
      </Card>

      <div className="card-grid card-grid--system">
        <Card title="Sistema">
          {data.system ? (
            <>
              <BarGauge
                value={data.system.cpu_percent}
                label={`CPU ${formatPercent(data.system.cpu_percent)}`}
                severity={gaugeSeverity(data.system.cpu_percent)}
              />
              {memPercent !== null && (
                <BarGauge
                  value={memPercent}
                  label={`RAM ${formatBytes(data.system.memory_used_bytes)} / ${formatBytes(data.system.memory_total_bytes)}`}
                  severity={gaugeSeverity(memPercent)}
                />
              )}
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
          <BarGauge
            value={data.storage.used_percent}
            label={`Storage ${formatPercent(data.storage.used_percent)}`}
            severity={
              thresholds
                ? gaugeSeverity(
                    data.storage.used_percent,
                    thresholds.warning_from,
                    thresholds.emergency_from,
                  )
                : gaugeSeverity(data.storage.used_percent, 70, 90)
            }
          />
        </Card>

        <Card title="Cronologia incidenti">
          <HeartbeatStrip events={incidents} days={30} />
          <IncidentHistoryList events={incidents} limit={3} compact />
        </Card>
      </div>

      <div className="card-grid card-grid--system">
        <Card title="Dispositivi più attivi">
          <DevicesMostActive devices={devices} />
        </Card>

        <Card title="Attività recente">
          <RecentActivity
            lastBackupAt={data.last_backup_at}
            lastBlocklistUpdateAt={data.last_blocklist_update_at}
            incidents={incidents}
            devices={devices}
          />
        </Card>
      </div>
    </div>
  );
}
