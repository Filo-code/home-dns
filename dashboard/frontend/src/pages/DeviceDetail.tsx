import { useEffect, useState } from "react";

import { ApiError } from "../api/client";
import { useApiClient } from "../api/useApiClient";
import type {
  DeviceActivity,
  DeviceView,
  DomainCount,
  HistoryResponse,
  QueryLogEntry,
} from "../api/types";
import { Card, StatRow } from "../components/Card";
import { LineChart } from "../components/charts/LineChart";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { Table, type Column } from "../components/Table";
import { useAuth } from "../context/AuthContext";
import { usePolling } from "../hooks/usePolling";
import { formatDateTime, formatLatency, formatNumber, formatPercent, formatTime } from "../lib/format";

const POLL_MS = 120_000;

const domainColumns: Column<DomainCount>[] = [
  { key: "domain", header: "Dominio", render: (row) => row.domain },
  { key: "count", header: "Richieste", render: (row) => formatNumber(row.count) },
];

const recentColumns: Column<QueryLogEntry>[] = [
  { key: "time", header: "Ora", render: (row) => formatDateTime(row.time) },
  { key: "domain", header: "Dominio", render: (row) => row.domain },
  { key: "outcome", header: "Esito", render: (row) => row.outcome },
  { key: "blocked_by", header: "Bloccato da", render: (row) => row.blocked_by ?? "—" },
  { key: "latency", header: "Latenza", render: (row) => formatLatency(row.latency_ms) },
];

export function DeviceDetail({ deviceId }: { deviceId: string }) {
  const id = Number(deviceId);
  const validId = Number.isInteger(id) && id > 0;
  const { get } = useApiClient();
  const { state } = useAuth();
  const isAdmin = state.role === "admin";

  const { data, error, loading, refresh } = usePolling<DeviceView>(
    // usePolling calls the fetcher unconditionally (hooks can't be called conditionally); guard
    // here instead so an invalid id never reaches the network at all.
    () =>
      validId
        ? get<DeviceView>(`/api/v1/devices/${id}`)
        : Promise.reject(new ApiError(404, "invalid device id")),
    POLL_MS,
    [id],
  );
  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [activity, setActivity] = useState<DeviceActivity | null>(null);
  const [activityError, setActivityError] = useState<unknown>(null);
  const [activityLoading, setActivityLoading] = useState(isAdmin);

  useEffect(() => {
    if (!validId) return;
    get<HistoryResponse>("/api/v1/metrics/history", {
      query: { resolution: "hour", device_id: id },
    })
      .then(setHistory)
      .catch(() => {
        // The overview stat cards already carry the important numbers; a missing chart is
        // non-fatal and shown as its own loading/empty state below.
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, validId]);

  useEffect(() => {
    // The admin-only fetch is never attempted for a viewer — not just refused by the
    // backend (docs/specs/a8-frontend-dashboard.md §12).
    if (!validId || !isAdmin) {
      setActivityLoading(false);
      return;
    }
    setActivityLoading(true);
    get<DeviceActivity>(`/api/v1/devices/${id}/activity`)
      .then(setActivity)
      .catch(setActivityError)
      .finally(() => setActivityLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, validId, isAdmin]);

  if (!validId) {
    return <ErrorState error={new ApiError(404, "device not found")} />;
  }
  if (loading && !data) return <LoadingState />;
  if (error && !data) return <ErrorState error={error} onRetry={refresh} />;
  if (!data) return null;

  return (
    <div className="page page--device-detail">
      <h1>{data.name}</h1>

      <div className="card-grid">
        <Card title="Informazioni">
          <StatRow label="Gruppo" value={data.group_id} />
          {isAdmin && <StatRow label="MAC" value={data.mac ?? "—"} />}
          {isAdmin && <StatRow label="Indirizzi" value={data.addresses.join(", ") || "—"} />}
          <StatRow label="Primo avvistamento" value={formatDateTime(data.first_seen)} />
          <StatRow label="Ultimo avvistamento" value={formatDateTime(data.last_seen)} />
        </Card>
        <Card title="Attività (24h)">
          <StatRow label="Totali" value={formatNumber(data.last_24h.total)} />
          <StatRow label="Bloccate" value={formatNumber(data.last_24h.blocked)} />
          <StatRow label="% bloccate" value={formatPercent(data.last_24h.block_percentage)} />
        </Card>
      </div>

      <Card title="Andamento query" className="card--wide">
        {history ? (
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

      {isAdmin ? (
        <Card title="Attività dettagliata" className="card--wide">
          {activityLoading ? (
            <LoadingState />
          ) : activityError ? (
            <ErrorState error={activityError} />
          ) : activity ? (
            <>
              {activity.truncated && (
                <p className="notice" role="status">
                  Mostrati solo i risultati più recenti: erano presenti più query di quante
                  analizzate.
                </p>
              )}
              <h3>Domini più richiesti</h3>
              {activity.top_domains.length === 0 ? (
                <EmptyState />
              ) : (
                <Table
                  columns={domainColumns}
                  rows={activity.top_domains}
                  rowKey={(row) => row.domain}
                  caption="Domini più richiesti"
                />
              )}
              <h3>Domini più bloccati</h3>
              {activity.top_blocked.length === 0 ? (
                <EmptyState />
              ) : (
                <Table
                  columns={domainColumns}
                  rows={activity.top_blocked}
                  rowKey={(row) => row.domain}
                  caption="Domini più bloccati"
                />
              )}
              <h3>Query recenti</h3>
              {activity.recent.length === 0 ? (
                <EmptyState />
              ) : (
                <Table
                  columns={recentColumns}
                  rows={activity.recent}
                  rowKey={(row) => row.id}
                  caption="Query recenti"
                />
              )}
            </>
          ) : null}
        </Card>
      ) : (
        <Card title="Attività dettagliata" className="card--wide">
          <p>Non hai i permessi per questa sezione.</p>
        </Card>
      )}
    </div>
  );
}
