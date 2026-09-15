import type { Severity } from "../components/StatusBadge";
import type { AnomalySeverity, HealthStatus, IncidentState } from "../api/types";

export function severityFromHealth(status: HealthStatus): Severity {
  switch (status) {
    case "ok":
      return "ok";
    case "degraded":
      return "warning";
    case "down":
      return "critical";
  }
}

export function severityFromIncident(state: IncidentState): Severity {
  switch (state) {
    case "ok":
      return "ok";
    case "suspect":
    case "recovering":
      return "warning";
    case "incident":
      return "critical";
  }
}

const HEALTH_LABEL_IT: Record<HealthStatus, string> = {
  ok: "attivo",
  degraded: "degradato",
  down: "non risponde",
};

export function healthLabelIt(status: HealthStatus): string {
  return HEALTH_LABEL_IT[status];
}

const INCIDENT_LABEL_IT: Record<IncidentState, string> = {
  ok: "normale",
  suspect: "sospetto",
  incident: "incidente",
  recovering: "in recupero",
};

export function incidentLabelIt(state: IncidentState): string {
  return INCIDENT_LABEL_IT[state];
}

// Deliberately calm mapping — "low"/"medium" both read as a routine "warning" badge, not an
// alarm; only "high" reads as "critical". The anomaly layer itself never claims certainty
// (core/anomaly.py), so the UI must not visually claim more confidence than the data has.
export function severityFromAnomaly(severity: AnomalySeverity): Severity {
  return severity === "high" ? "critical" : "warning";
}

const ANOMALY_SEVERITY_LABEL_IT: Record<AnomalySeverity, string> = {
  low: "bassa",
  medium: "media",
  high: "alta",
};

export function anomalySeverityLabelIt(severity: AnomalySeverity): string {
  return ANOMALY_SEVERITY_LABEL_IT[severity];
}

const ANOMALY_SIGNAL_LABEL_IT: Record<string, string> = {
  nxdomain_burst: "picco NXDOMAIN",
  query_rate_spike: "picco di query",
  beaconing: "intervallo regolare ripetuto",
  high_entropy_domain: "dominio dall'aspetto casuale",
  repeated_failures: "errori di risoluzione ripetuti",
};

export function anomalySignalLabelIt(signal: string): string {
  return ANOMALY_SIGNAL_LABEL_IT[signal] ?? signal;
}
