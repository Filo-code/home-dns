import type { AnomalyView } from "../api/types";
import { formatDateTime } from "../lib/format";
import { anomalySeverityLabelIt, anomalySignalLabelIt, severityFromAnomaly } from "../lib/severity";
import { EmptyState } from "./EmptyState";
import { StatusBadge } from "./StatusBadge";

/** Read-only presentation of the passive anomaly-detection layer (core/anomaly.py). Never
 * implies certainty — every row shows the named signals and the deterministic ``reason``
 * sentence the backend already computed, not a re-interpreted verdict. */
export function AnomalyList({ anomalies, limit }: { anomalies: AnomalyView[]; limit?: number }) {
  const shown = limit ? anomalies.slice(0, limit) : anomalies;
  if (shown.length === 0) {
    return <EmptyState label="Nessuna anomalia rilevata." />;
  }
  return (
    <ul className="anomaly-list">
      {shown.map((anomaly) => (
        <li key={anomaly.id} className="anomaly-list__row">
          <StatusBadge
            severity={severityFromAnomaly(anomaly.severity)}
            label={anomalySeverityLabelIt(anomaly.severity)}
          />
          <span className="anomaly-list__text">
            <b>dispositivo #{anomaly.device_id}</b> — {anomaly.reason}
            <span className="anomaly-list__signals">
              {" "}
              ({anomaly.signals.map(anomalySignalLabelIt).join(", ")})
            </span>
          </span>
          <span className="anomaly-list__time">{formatDateTime(anomaly.detected_at)}</span>
        </li>
      ))}
    </ul>
  );
}
