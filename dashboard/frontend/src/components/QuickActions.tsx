import { Link, alertsPath, devicesPath } from "../router";
import { useOverview } from "../context/OverviewContext";
import { isAdmin } from "../lib/roles";
import type { Role } from "../api/types";
import {
  IconBackup,
  IconBlocklist,
  IconDevices,
  IconAlerts,
  IconPulse,
  IconRefresh,
} from "./icons";

export type AdminAction = "backup" | "blocklist";

/**
 * Lives on the Overview page (not the shell) — the mockup's quick-actions row is page content.
 * Viewers never see the two administrative buttons at all (RBAC honesty: matches the existing
 * pattern where the "Registro query" nav item is invisible to a viewer, not just disabled).
 */
export function QuickActions({
  role,
  onRequestAdminAction,
}: {
  role: Role | null;
  onRequestAdminAction: (action: AdminAction) => void;
}) {
  const { refresh, refreshAll } = useOverview();

  return (
    <div className="quick-actions">
      <button type="button" className="quick-action quick-action--primary" onClick={refresh}>
        <IconRefresh /> Aggiorna dati
      </button>
      <button type="button" className="quick-action" onClick={refreshAll}>
        <IconPulse /> Health check
      </button>
      <Link to={alertsPath()} className="quick-action">
        <IconAlerts /> Vedi avvisi
      </Link>
      <Link to={devicesPath()} className="quick-action">
        <IconDevices /> Vedi dispositivi
      </Link>
      {isAdmin(role) && (
        <>
          <button
            type="button"
            className="quick-action quick-action--admin"
            onClick={() => onRequestAdminAction("backup")}
          >
            <IconBackup /> Backup
            <span className="quick-action__tag">admin</span>
          </button>
          <button
            type="button"
            className="quick-action quick-action--admin"
            onClick={() => onRequestAdminAction("blocklist")}
          >
            <IconBlocklist /> Aggiorna blocklist
            <span className="quick-action__tag">admin</span>
          </button>
        </>
      )}
    </div>
  );
}
