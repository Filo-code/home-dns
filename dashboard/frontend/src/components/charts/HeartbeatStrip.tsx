import type { IncidentEventView } from "../../api/types";
import { buildHeartbeat } from "../../lib/heartbeat";

const LABEL_IT: Record<string, string> = {
  ok: "normale",
  warning: "attenzione",
  critical: "critico",
  unknown: "nessun dato",
};

/** One bar per day, colored by the worst incident state that day, reconstructed from the
 * persisted opened/recovered event log (never color alone — every bar carries a title). */
export function HeartbeatStrip({
  events,
  days = 30,
}: {
  events: IncidentEventView[];
  days?: number;
}) {
  const timeline = buildHeartbeat(events, days);
  return (
    <div className="heartbeat-strip">
      <div
        className="heartbeat-strip__bars"
        role="img"
        aria-label={`stato degli ultimi ${days} giorni`}
      >
        {timeline.map((day) => (
          <span
            key={day.date}
            className={`heartbeat-strip__bar heartbeat-strip__bar--${day.severity}`}
            title={`${day.date}: ${LABEL_IT[day.severity]}`}
          />
        ))}
      </div>
      <div className="heartbeat-strip__caption">
        <span>{days} giorni fa</span>
        <span>ora</span>
      </div>
    </div>
  );
}
