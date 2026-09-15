import type { ReactElement } from "react";

import type { DeviceView, IncidentEventView } from "../api/types";
import { formatDateTime } from "../lib/format";
import { EmptyState } from "./EmptyState";
import { IconBackup, IconBlocklist, IconCheck, IconDevices, IconWarn } from "./icons";
import type { IconProps } from "./icons";

interface ActivityItem {
  id: string;
  icon: (props: IconProps) => ReactElement;
  tone: "ok" | "warning" | "info";
  text: string;
  at: string;
}

const TRANSITION_TEXT_IT: Record<string, string> = {
  opened: "aperto",
  recovered: "recuperato",
};

/**
 * Summarizes the same fields already available elsewhere on this page (backup/blocklist
 * timestamps, the incident event log, device first-seen) into one chronological list — no
 * new "activity feed" endpoint, deliberately not a broader event log than these fields give.
 */
export function RecentActivity({
  lastBackupAt,
  lastBlocklistUpdateAt,
  incidents,
  devices,
}: {
  lastBackupAt: string | null;
  lastBlocklistUpdateAt: string | null;
  incidents: IncidentEventView[];
  devices: DeviceView[];
}) {
  const items: ActivityItem[] = [];

  if (lastBackupAt) {
    items.push({
      id: "backup",
      icon: IconBackup,
      tone: "ok",
      text: "Backup completato",
      at: lastBackupAt,
    });
  }
  if (lastBlocklistUpdateAt) {
    items.push({
      id: "blocklist",
      icon: IconBlocklist,
      tone: "ok",
      text: "Blocklist aggiornata",
      at: lastBlocklistUpdateAt,
    });
  }

  const newestDevice = devices.reduce<DeviceView | null>(
    (newest, device) =>
      newest === null || device.first_seen > newest.first_seen ? device : newest,
    null,
  );
  if (newestDevice) {
    items.push({
      id: `device-${newestDevice.device_id}`,
      icon: IconDevices,
      tone: "info",
      text: `Nuovo dispositivo rilevato: ${newestDevice.name}`,
      at: newestDevice.first_seen,
    });
  }

  for (const event of incidents) {
    items.push({
      id: `${event.check_name}-${event.occurred_at}`,
      icon: event.transition === "recovered" ? IconCheck : IconWarn,
      tone: event.transition === "recovered" ? "ok" : "warning",
      text: `Incidente ${event.check_name} ${TRANSITION_TEXT_IT[event.transition]}`,
      at: event.occurred_at,
    });
  }

  items.sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime());
  const shown = items.slice(0, 6);

  if (shown.length === 0) {
    return <EmptyState label="Nessuna attività recente." />;
  }

  return (
    <ul className="incident-history">
      {shown.map((item) => (
        <li key={item.id} className="incident-history__row">
          <span
            aria-hidden="true"
            className={`incident-history__icon incident-history__icon--${item.tone}`}
          >
            <item.icon size={13} />
          </span>
          <span className="incident-history__text">{item.text}</span>
          <span className="incident-history__time">{formatDateTime(item.at)}</span>
        </li>
      ))}
    </ul>
  );
}
