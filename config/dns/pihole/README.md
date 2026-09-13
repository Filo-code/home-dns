# Pi-hole configuration (planned)

> **Status: not written.** Pi-hole is **not installed** (ADR 0001). No `pihole.toml` values are committed yet.

Planned approach (Phase 6):
- Track only the settings we deliberately change, with the reason for each, instead of a full copy of `pihole.toml`.
- Apply them through the official API or `pihole-FTL --config`, never by editing internal databases.

Defaults already known to need a decision (from `docs/architecture-comparison.md`):

| Setting | Upstream default | Project note |
|---|---|---|
| `database.maxDBdays` | 91 | Target ~30 days (CLAUDE.md §16) |
| `database.DBinterval` | 60 s | Choose from Pi audit storage data |
| `webserver.api.app_sudo` | false | Decide whether the backend's app password needs write access |
| `dns.upstreams` | — | `127.0.0.1#5335` (Unbound) once installed |
| `dns.specialDomains.mozillaCanary` / `iCloudPrivateRelay` / `designatedResolver` | true | Keep; document effects |
| `dns.CNAMEdeepInspect` | true | Keep |
