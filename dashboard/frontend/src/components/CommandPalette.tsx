import { useEffect, useMemo, useRef, useState, type ReactElement } from "react";

import type { Role } from "../api/types";
import type { AdminAction } from "./QuickActions";
import { isAdmin } from "../lib/roles";
import {
  alertsPath,
  devicesPath,
  navigate,
  overviewPath,
  queriesPath,
  securityPath,
  systemPath,
} from "../router";
import {
  IconAlerts,
  IconBackup,
  IconBlocklist,
  IconDevices,
  IconOverview,
  IconQueries,
  IconSecurity,
  IconSystem,
} from "./icons";
import type { IconProps } from "./icons";

interface Command {
  id: string;
  label: string;
  icon: (props: IconProps) => ReactElement;
  adminOnly?: boolean;
  admin?: boolean; // rendered with an "admin" tag, distinct from adminOnly (visibility)
  run: () => void;
}

/**
 * ⌘K/Ctrl+K. A static, role-filtered command list — a viewer never sees "Aggiorna blocklist" or
 * "Backup" here, same visibility rule as QuickActions and the Registro-query nav item. Built on
 * <dialog> for the same free focus-trap/Esc-to-close reasoning as ActionSheet.
 */
export function CommandPalette({
  open,
  role,
  onClose,
  onRequestAdminAction,
}: {
  open: boolean;
  role: Role | null;
  onClose: () => void;
  onRequestAdminAction: (action: AdminAction) => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
      setQuery("");
      inputRef.current?.focus();
    }
    if (!open && dialog.open) dialog.close();
  }, [open]);

  const goto = (path: string) => () => {
    navigate(path);
    onClose();
  };

  const commands = useMemo<Command[]>(
    () => [
      {
        id: "admin-blocklist",
        label: "Aggiorna blocklist",
        icon: IconBlocklist,
        adminOnly: true,
        admin: true,
        run: () => {
          onRequestAdminAction("blocklist");
          onClose();
        },
      },
      {
        id: "admin-backup",
        label: "Backup ora",
        icon: IconBackup,
        adminOnly: true,
        admin: true,
        run: () => {
          onRequestAdminAction("backup");
          onClose();
        },
      },
      { id: "go-overview", label: "Panoramica", icon: IconOverview, run: goto(overviewPath()) },
      { id: "go-devices", label: "Dispositivi", icon: IconDevices, run: goto(devicesPath()) },
      { id: "go-security", label: "Sicurezza", icon: IconSecurity, run: goto(securityPath()) },
      { id: "go-system", label: "Sistema", icon: IconSystem, run: goto(systemPath()) },
      { id: "go-alerts", label: "Avvisi", icon: IconAlerts, run: goto(alertsPath()) },
      {
        id: "go-queries",
        label: "Registro query",
        icon: IconQueries,
        adminOnly: true,
        run: goto(queriesPath()),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [role],
  );

  const visible = commands.filter((c) => !c.adminOnly || isAdmin(role));
  const filtered =
    query.trim() === ""
      ? visible
      : visible.filter((c) => c.label.toLowerCase().includes(query.trim().toLowerCase()));

  return (
    <dialog ref={ref} className="command-palette" onClose={onClose}>
      {/* A closed <dialog> is only hidden via the UA stylesheet, which jsdom does not apply —
       * its content must not render at all while closed, or its text becomes findable/
       * ambiguous against identically-labelled visible elements (e.g. Nav's own links). */}
      {open && (
        <>
          <div className="command-palette__input">
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Vai a, cerca un dispositivo, esegui un'azione…"
              aria-label="Comando"
            />
            <kbd>esc</kbd>
          </div>
          <ul className="command-palette__list">
            {filtered.map((command) => (
              <li key={command.id}>
                <button type="button" className="command-palette__item" onClick={command.run}>
                  <command.icon size={15} />
                  {command.label}
                  {command.admin && <span className="command-palette__tag">admin</span>}
                </button>
              </li>
            ))}
            {filtered.length === 0 && (
              <li className="command-palette__empty">Nessun comando corrispondente.</li>
            )}
          </ul>
        </>
      )}
    </dialog>
  );
}
