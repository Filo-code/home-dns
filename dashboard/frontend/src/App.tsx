import { useEffect } from "react";

import { LoadingState } from "./components/LoadingState";
import { Nav } from "./components/Nav";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { Login } from "./pages/Login";
import { Overview } from "./pages/Overview";
import { Devices } from "./pages/Devices";
import { DeviceDetail } from "./pages/DeviceDetail";
import { Security } from "./pages/Security";
import { System } from "./pages/System";
import { Alerts } from "./pages/Alerts";
import { QueryLog } from "./pages/QueryLog";
import { intendedPath, loginPath, navigate, useRoute, type Route } from "./router";

function PageFor({ route, role }: { route: Route; role: "admin" | "viewer" | null }) {
  switch (route.name) {
    case "overview":
      return <Overview />;
    case "devices":
      return <Devices />;
    case "device-detail":
      return <DeviceDetail deviceId={route.params.id ?? ""} />;
    case "security":
      return <Security />;
    case "system":
      return <System />;
    case "alerts":
      return <Alerts />;
    case "queries":
      return role === "admin" ? (
        <QueryLog />
      ) : (
        <div className="state state--error" role="alert">
          <p>Non hai i permessi per questa sezione.</p>
        </div>
      );
    case "login":
      return null; // handled by AppShell before reaching here
    case "not-found":
      return (
        <div className="state state--empty">
          <p>Pagina non trovata.</p>
        </div>
      );
  }
}

function AppShell() {
  const { state } = useAuth();
  const route = useRoute();

  useEffect(() => {
    if (state.status === "anonymous" && route.name !== "login") {
      const current = window.location.pathname + window.location.search;
      navigate(loginPath(current), { replace: true });
    }
    if (state.status === "authenticated" && route.name === "login") {
      navigate(intendedPath(), { replace: true });
    }
  }, [state.status, route.name]);

  if (state.status === "loading") {
    return <LoadingState label="Caricamento…" />;
  }
  if (state.status === "anonymous") {
    return route.name === "login" ? <Login /> : <LoadingState />;
  }
  if (route.name === "login") {
    return <LoadingState />;
  }

  return (
    <div className="app-shell">
      <Nav role={state.role} />
      <main id="main-content" className="app-shell__content">
        <PageFor route={route} role={state.role} />
      </main>
    </div>
  );
}

export function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  );
}
