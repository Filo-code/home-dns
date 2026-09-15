import type { IncidentEventView } from "../api/types";
import { formatDateTime } from "../lib/format";
import { EmptyState } from "./EmptyState";

const TRANSITION_LABEL_IT: Record<string, string> = {
  opened: "aperto",
  recovered: "recuperato",
};

const SEVERITY_LABEL_IT: Record<string, string> = {
  critical: "critico",
  warning: "attenzione",
  info: "info",
};

/** Same component for the compact Overview card and the fuller Alerts-page list — `limit`
 * controls how many rows show, `compact` drops the check-name column for the narrow layout. */
export function IncidentHistoryList({
  events,
  limit,
  compact = false,
}: {
  events: IncidentEventView[];
  limit?: number;
  compact?: boolean;
}) {
  const shown = limit ? events.slice(0, limit) : events;
  if (shown.length === 0) {
    return <EmptyState label="Nessun incidente registrato." />;
  }
  return (
    <ul className="incident-history">
      {shown.map((event, index) => (
        <li
          key={`${event.check_name}-${event.occurred_at}-${index}`}
          className="incident-history__row"
        >
          <span
            aria-hidden="true"
            className={`incident-history__icon incident-history__icon--${
              event.transition === "recovered" ? "ok" : event.severity || "warning"
            }`}
          />
          <span className="incident-history__text">
            {!compact && <b>{event.check_name}</b>} {TRANSITION_LABEL_IT[event.transition]}
            {event.severity && ` (${SEVERITY_LABEL_IT[event.severity]})`}
          </span>
          <span className="incident-history__time">{formatDateTime(event.occurred_at)}</span>
        </li>
      ))}
    </ul>
  );
}
