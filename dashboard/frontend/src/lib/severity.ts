import type { Severity } from "../components/StatusBadge";
import type { HealthStatus, IncidentState } from "../api/types";

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
