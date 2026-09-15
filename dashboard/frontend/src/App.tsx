import { useCallback, useEffect, useState } from "react";

import { ActionSheet } from "./components/ActionSheet";
import { CommandPalette } from "./components/CommandPalette";
import { LoadingState } from "./components/LoadingState";
import { Nav } from "./components/Nav";
import type { AdminAction } from "./components/QuickActions";
import { TopBar } from "./components/TopBar";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { OverviewProvider } from "./context/OverviewContext";
import { Login } from "./pages/Login";
import { Overview } from "./pages/Overview";
import { Devices } from "./pages/Devices";
import { DeviceDetail } from "./pages/DeviceDetail";
import { Security } from "./pages/Security";
import { System } from "./pages/System";
import { Alerts } from "./pages/Alerts";
import { QueryLog } from "./pages/QueryLog";
import { intendedPath, loginPath, navigate, useRoute, type Route } from "./router";

const ADMIN_ACTION_COPY: Record<AdminAction, { title: string; description: string }> = {
  blocklist: {
    title: "Aggiornare la blocklist ora?",
    description:
      "L'aggiornamento manuale delle blocklist da qui non è ancora disponibile in questa " +
      "versione della dashboard. Le liste si aggiornano secondo la pianificazione automatica " +
      "configurata sul sistema.",
  },
  backup: {
    title: "Eseguire un backup ora?",
    description:
      "L'avvio di un backup manuale da qui non è ancora disponibile in questa versione della " +
      "dashboard. I backup vengono eseguiti secondo la pianificazione automatica configurata " +
      "sul sistema.",
  },
};

function PageFor({
  route,
  role,
  onRequestAdminAction,
}: {
  route: Route;
  role: "admin" | "viewer" | null;
  onRequestAdminAction: (action: AdminAction) => void;
}) {
  switch (route.name) {
    case "overview":
      return <Overview role={role} onRequestAdminAction={onRequestAdminAction} />;
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
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [pendingAdminAction, setPendingAdminAction] = useState<AdminAction | null>(null);

  useEffect(() => {
    if (state.status === "anonymous" && route.name !== "login") {
      const current = window.location.pathname + window.location.search;
      navigate(loginPath(current), { replace: true });
    }
    if (state.status === "authenticated" && route.name === "login") {
      navigate(intendedPath(), { replace: true });
    }
  }, [state.status, route.name]);

  useEffect(() => {
    if (state.status !== "authenticated") return;
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [state.status]);

  const requestAdminAction = useCallback((action: AdminAction) => {
    setPendingAdminAction(action);
  }, []);

  if (state.status === "loading") {
    return <LoadingState label="Caricamento…" />;
  }
  if (state.status === "anonymous") {
    return route.name === "login" ? <Login /> : <LoadingState />;
  }
  if (route.name === "login") {
    return <LoadingState />;
  }

  const adminActionCopy = pendingAdminAction ? ADMIN_ACTION_COPY[pendingAdminAction] : null;

  return (
    <OverviewProvider>
      <div className="app-shell">
        <Nav role={state.role} />
        <div className="app-shell__main">
          <TopBar onOpenPalette={() => setPaletteOpen(true)} />
          <main id="main-content" className="app-shell__content">
            <PageFor route={route} role={state.role} onRequestAdminAction={requestAdminAction} />
          </main>
        </div>
      </div>
      <CommandPalette
        open={paletteOpen}
        role={state.role}
        onClose={() => setPaletteOpen(false)}
        onRequestAdminAction={requestAdminAction}
      />
      <ActionSheet
        open={pendingAdminAction !== null}
        title={adminActionCopy?.title ?? ""}
        badge="Operazione amministrativa"
        description={adminActionCopy?.description ?? ""}
        onClose={() => setPendingAdminAction(null)}
      />
    </OverviewProvider>
  );
}

export function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  );
}
