# deployment/

| Directory | Purpose | Status |
|---|---|---|
| `systemd/` | Units/timers for our own services and jobs (monitoring, backups, dashboard) | `home-dns-dashboard.service` added (Phase C4, [docs/deployment/raspberry-pi.md](../docs/deployment/raspberry-pi.md)); not yet installed on the real Pi |
| `nginx/` | Reverse proxy for the dashboard **only if** ADR 0005 requires one | Not used — [ADR 0010](../docs/adr/0010-frontend-hosting.md) confirms no reverse proxy is needed; reserved, may be removed |

`deployment/docker/` from the original CLAUDE.md layout is **intentionally omitted**. ADR 0001 selects a native install, to avoid an unnecessary container layer and keep host ARP/NDP visibility.
