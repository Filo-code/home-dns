import type { DeviceView } from "../api/types";
import { formatNumber } from "../lib/format";
import { deviceDetailPath, Link } from "../router";
import { EmptyState } from "./EmptyState";

/** Client-side sort of the already-fetched device list by 24h query volume — no new
 * backend endpoint, matches the mockup's "Dispositivi più attivi" card. */
export function DevicesMostActive({
  devices,
  limit = 6,
}: {
  devices: DeviceView[];
  limit?: number;
}) {
  const sorted = [...devices].sort((a, b) => b.last_24h.total - a.last_24h.total).slice(0, limit);
  if (sorted.length === 0) {
    return <EmptyState label="Nessun dispositivo ancora rilevato." />;
  }
  const max = Math.max(...sorted.map((d) => d.last_24h.total), 1);

  return (
    <ul className="device-activity">
      {sorted.map((device) => (
        <li key={device.device_id} className="device-activity__row">
          <Link to={deviceDetailPath(device.device_id)} className="device-activity__name">
            {device.name}
          </Link>
          <div
            className="device-activity__bar-track"
            role="meter"
            aria-valuenow={device.last_24h.total}
            aria-valuemin={0}
            aria-valuemax={max}
            aria-label={`Query nelle ultime 24 ore per ${device.name}`}
          >
            <div
              className="device-activity__bar-fill"
              style={{ width: `${(device.last_24h.total / max) * 100}%` }}
            />
          </div>
          <span className="device-activity__count">{formatNumber(device.last_24h.total)}</span>
        </li>
      ))}
    </ul>
  );
}
