import { useOverview } from "../context/OverviewContext";
import { alertsPath, Link, useRoute, type RouteName } from "../router";
import { formatTime } from "../lib/format";
import { IconBell, IconRefresh, IconSearch } from "./icons";

const ROUTE_LABEL_IT: Record<RouteName, string> = {
  overview: "Panoramica",
  devices: "Dispositivi",
  "device-detail": "Dispositivo",
  security: "Sicurezza",
  system: "Sistema",
  alerts: "Avvisi",
  queries: "Registro query",
  login: "Accesso",
  "not-found": "Pagina non trovata",
};

/** Shell-level: breadcrumb, "updated at", ⌘K trigger, refresh, and a notifications link badged
 * from the live open-incident count already returned by /overview (nothing invented here). */
export function TopBar({ onOpenPalette }: { onOpenPalette: () => void }) {
  const route = useRoute();
  const { overview, updatedAt, refresh } = useOverview();
  const openIncidents = overview?.open_incidents ?? 0;

  return (
    <div className="topbar">
      <span className="topbar__crumb">{ROUTE_LABEL_IT[route.name]}</span>
      <div className="topbar__actions">
        {updatedAt && (
          <span className="topbar__updated">
            <span aria-hidden="true" className="topbar__live-dot" />
            aggiornato alle {formatTime(updatedAt.toISOString())}
          </span>
        )}
        <button type="button" className="topbar__palette-trigger" onClick={onOpenPalette}>
          <IconSearch size={14} /> Cerca o esegui
          <kbd>⌘K</kbd>
        </button>
        <button
          type="button"
          className="topbar__icon-button"
          onClick={refresh}
          aria-label="Aggiorna"
        >
          <IconRefresh size={16} />
        </button>
        <Link to={alertsPath()} className="topbar__icon-button" aria-label="Avvisi">
          <IconBell size={16} />
          {openIncidents > 0 && <span className="topbar__ping" aria-hidden="true" />}
        </Link>
      </div>
    </div>
  );
}
