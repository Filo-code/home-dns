import { useEffect, useState } from "react";

import { useAuth } from "../context/AuthContext";
import { useOverview } from "../context/OverviewContext";
import { useApiClient } from "../api/useApiClient";
import { computeHealth } from "../lib/health";
import { isAdmin } from "../lib/roles";
import {
  Link,
  alertsPath,
  devicesPath,
  loginPath,
  navigate,
  overviewPath,
  queriesPath,
  securityPath,
  systemPath,
  useRoute,
  type RouteName,
} from "../router";
import type { Role } from "../api/types";
import { HealthRing } from "./HealthRing";
import {
  IconAlerts,
  IconChevron,
  IconDevices,
  IconOverview,
  IconQueries,
  IconSecurity,
  IconSystem,
} from "./icons";

const NAV_ITEMS: { to: string; label: string; name: RouteName; icon: typeof IconOverview }[] = [
  { to: overviewPath(), label: "Panoramica", name: "overview", icon: IconOverview },
  { to: devicesPath(), label: "Dispositivi", name: "devices", icon: IconDevices },
  { to: securityPath(), label: "Sicurezza", name: "security", icon: IconSecurity },
  { to: systemPath(), label: "Sistema", name: "system", icon: IconSystem },
  { to: alertsPath(), label: "Avvisi", name: "alerts", icon: IconAlerts },
];

const COLLAPSE_STORAGE_KEY = "home-dns:nav-collapsed";

export function Nav({ role }: { role: Role | null }) {
  const { state, setAnonymous } = useAuth();
  const { overview, config } = useOverview();
  const { mutate } = useApiClient();
  const route = useRoute();

  const [collapsed, setCollapsed] = useState(() => {
    try {
      return window.localStorage.getItem(COLLAPSE_STORAGE_KEY) === "1";
    } catch {
      return false; // a private window or blocked storage never breaks navigation
    }
  });

  useEffect(() => {
    try {
      window.localStorage.setItem(COLLAPSE_STORAGE_KEY, collapsed ? "1" : "0");
    } catch {
      // per-viewer convenience only; nothing to recover from here
    }
  }, [collapsed]);

  async function handleLogout() {
    try {
      await mutate<void>("/api/v1/auth/logout", "POST");
    } finally {
      setAnonymous();
      navigate(loginPath(), { replace: true });
    }
  }

  const isActive = (name: RouteName) =>
    route.name === name || (name === "devices" && route.name === "device-detail");

  const health = overview ? computeHealth(overview, config) : null;

  return (
    <nav
      className={`nav${collapsed ? " nav--collapsed" : ""}`}
      aria-label="Navigazione principale"
    >
      <div className="nav__brand">
        <span className="nav__brand-mark" aria-hidden="true" />
        <span className="nav__brand-word">Home DNS</span>
      </div>

      {health && (
        <div className="nav__health">
          <HealthRing score={health.score} size="sm" />
          <div className="nav__health-text">
            <b>{health.score}%</b>
            <span>{health.bandLabel}</span>
          </div>
        </div>
      )}

      <ul className="nav__links">
        {NAV_ITEMS.map((item) => (
          <li key={item.to}>
            <Link
              to={item.to}
              className={isActive(item.name) ? "nav__link nav__link--active" : "nav__link"}
              aria-current={isActive(item.name) ? "page" : undefined}
            >
              <item.icon size={17} />
              <span>{item.label}</span>
            </Link>
          </li>
        ))}
        {isAdmin(role) && (
          <li>
            <Link
              to={queriesPath()}
              className={isActive("queries") ? "nav__link nav__link--active" : "nav__link"}
              aria-current={isActive("queries") ? "page" : undefined}
            >
              <IconQueries size={17} />
              <span>Registro query</span>
            </Link>
          </li>
        )}
      </ul>
      <div className="nav__user">
        <span className="nav__username">{state.username}</span>
        <button
          type="button"
          className="button button--secondary"
          onClick={() => void handleLogout()}
        >
          Esci
        </button>
        <button
          type="button"
          className="nav__collapse-toggle"
          onClick={() => setCollapsed((value) => !value)}
          aria-label={collapsed ? "Espandi la barra laterale" : "Comprimi la barra laterale"}
        >
          <IconChevron
            size={13}
            style={{ transform: collapsed ? undefined : "rotate(180deg)" }}
          />
        </button>
      </div>
    </nav>
  );
}
