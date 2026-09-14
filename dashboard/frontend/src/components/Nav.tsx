import { useAuth } from "../context/AuthContext";
import { useApiClient } from "../api/useApiClient";
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

const NAV_ITEMS: { to: string; label: string; name: RouteName }[] = [
  { to: overviewPath(), label: "Panoramica", name: "overview" },
  { to: devicesPath(), label: "Dispositivi", name: "devices" },
  { to: securityPath(), label: "Sicurezza", name: "security" },
  { to: systemPath(), label: "Sistema", name: "system" },
  { to: alertsPath(), label: "Avvisi", name: "alerts" },
];

export function Nav({ role }: { role: Role | null }) {
  const { state, setAnonymous } = useAuth();
  const { mutate } = useApiClient();
  const route = useRoute();

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

  return (
    <nav className="nav" aria-label="Navigazione principale">
      <div className="nav__brand">Home DNS</div>
      <ul className="nav__links">
        {NAV_ITEMS.map((item) => (
          <li key={item.to}>
            <Link
              to={item.to}
              className={isActive(item.name) ? "nav__link nav__link--active" : "nav__link"}
              aria-current={isActive(item.name) ? "page" : undefined}
            >
              {item.label}
            </Link>
          </li>
        ))}
        {role === "admin" && (
          <li>
            <Link
              to={queriesPath()}
              className={isActive("queries") ? "nav__link nav__link--active" : "nav__link"}
              aria-current={isActive("queries") ? "page" : undefined}
            >
              Registro query
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
      </div>
    </nav>
  );
}
