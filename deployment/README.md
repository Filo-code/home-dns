# deployment/

| Directory | Purpose | Status |
|---|---|---|
| `systemd/` | Units/timers for our own services and jobs (monitoring, backups, dashboard) | Empty until Phase 12–14 |
| `nginx/` | Reverse proxy for the dashboard **only if** ADR 0005 requires one | Reserved; may be removed |

`deployment/docker/` from the original CLAUDE.md layout is **intentionally omitted**. ADR 0001 selects a native install, to avoid an unnecessary container layer and keep host ARP/NDP visibility.
