import { useEffect, useState } from "react";

import { useApiClient } from "../api/useApiClient";
import type { ConfigView, DeviceView } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { Table, type Column } from "../components/Table";
import { useAuth } from "../context/AuthContext";
import { usePolling } from "../hooks/usePolling";
import { formatDateTime, formatNumber, formatPercent } from "../lib/format";
import { deviceDetailPath, Link } from "../router";

const POLL_MS = 120_000;

function RenameControl({
  device,
  disabled,
  onSave,
}: {
  device: DeviceView;
  disabled: boolean;
  onSave: (name: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(device.custom_name ?? "");

  if (!editing) {
    return (
      <button
        type="button"
        className="link-button device-name-cell__rename"
        onClick={() => {
          setValue(device.custom_name ?? "");
          setEditing(true);
        }}
      >
        Rinomina
      </button>
    );
  }

  return (
    <form
      className="inline-edit"
      onSubmit={(event) => {
        event.preventDefault();
        onSave(value);
        setEditing(false);
      }}
    >
      <input
        value={value}
        onChange={(event) => setValue(event.target.value)}
        disabled={disabled}
        aria-label={`Nome personalizzato per ${device.name}`}
        maxLength={64}
      />
      <button type="submit" className="button button--secondary" disabled={disabled}>
        Salva
      </button>
      <button
        type="button"
        className="button button--secondary"
        onClick={() => setEditing(false)}
      >
        Annulla
      </button>
    </form>
  );
}

export function Devices() {
  const { get, mutate } = useApiClient();
  const { state } = useAuth();
  const isAdmin = state.role === "admin";
  const { data, error, loading, refresh } = usePolling<DeviceView[]>(
    () => get<DeviceView[]>("/api/v1/devices"),
    POLL_MS,
  );
  const [groups, setGroups] = useState<ConfigView["groups"]>([]);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [saveError, setSaveError] = useState<unknown>(null);

  useEffect(() => {
    if (!isAdmin) return;
    get<ConfigView>("/api/v1/config")
      .then((config) => setGroups(config.groups))
      .catch(() => {
        // Non-fatal: the group <select> just stays empty; the rest of the page still works.
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin]);

  async function handleGroupChange(deviceId: number, groupId: string) {
    setSavingId(deviceId);
    setSaveError(null);
    try {
      await mutate(`/api/v1/devices/${deviceId}`, "PATCH", { group_id: groupId });
      refresh();
    } catch (err) {
      setSaveError(err);
    } finally {
      setSavingId(null);
    }
  }

  async function handleRename(deviceId: number, customName: string) {
    setSavingId(deviceId);
    setSaveError(null);
    try {
      await mutate(`/api/v1/devices/${deviceId}`, "PATCH", { custom_name: customName });
      refresh();
    } catch (err) {
      setSaveError(err);
    } finally {
      setSavingId(null);
    }
  }

  if (loading && !data) return <LoadingState />;
  if (error && !data) return <ErrorState error={error} onRetry={refresh} />;
  if (!data) return null;

  const columns: Column<DeviceView>[] = [
    {
      key: "name",
      header: "Nome",
      render: (device) => (
        <div className="device-name-cell">
          <Link to={deviceDetailPath(device.device_id)}>{device.name}</Link>
          {isAdmin && (
            <RenameControl
              device={device}
              disabled={savingId === device.device_id}
              onSave={(name) => void handleRename(device.device_id, name)}
            />
          )}
        </div>
      ),
    },
    {
      key: "group",
      header: "Gruppo",
      render: (device) =>
        isAdmin ? (
          <select
            value={device.group_id}
            disabled={savingId === device.device_id}
            onChange={(event) => void handleGroupChange(device.device_id, event.target.value)}
            aria-label={`Gruppo per ${device.name}`}
          >
            {groups.some((g) => g.id === device.group_id) ? null : (
              <option value={device.group_id}>{device.group_id}</option>
            )}
            {groups.map((group) => (
              <option key={group.id} value={group.id}>
                {group.id}
              </option>
            ))}
          </select>
        ) : (
          device.group_id
        ),
    },
    ...(isAdmin
      ? [
          {
            key: "mac",
            header: "MAC",
            render: (device: DeviceView) => device.mac ?? "—",
          } satisfies Column<DeviceView>,
        ]
      : []),
    {
      key: "first_seen",
      header: "Primo avvistamento",
      render: (device) => formatDateTime(device.first_seen),
    },
    {
      key: "last_seen",
      header: "Ultimo avvistamento",
      render: (device) => formatDateTime(device.last_seen),
    },
    {
      key: "total",
      header: "Query (24h)",
      render: (device) => formatNumber(device.last_24h.total),
    },
    {
      key: "block_pct",
      header: "% bloccate",
      render: (device) => formatPercent(device.last_24h.block_percentage),
    },
  ];

  return (
    <div className="page page--devices">
      <h1>Dispositivi</h1>
      {saveError != null && <ErrorState error={saveError} />}
      {data.length === 0 ? (
        <EmptyState />
      ) : (
        <Table
          columns={columns}
          rows={data}
          rowKey={(device) => device.device_id}
          caption="Elenco dispositivi"
        />
      )}
    </div>
  );
}
