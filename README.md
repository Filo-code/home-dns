# home-dns

Home DNS security, ad blocking, performance monitoring and a custom LAN-only dashboard, running on a Raspberry Pi 4.

> **Project status: Stage A complete + dashboard redesigned. Stage B in progress (B1 done, waiting on B2).**
> Nothing has been installed or deployed to the Raspberry Pi. No DNS, DHCP, IPv4, IPv6, firewall, router or
> production service has been changed. Stage A (all offline software, A0–A9) is finished and tested, the
> dashboard has since had a full visual redesign ("Night Ops"), and the Raspberry Pi hardware/OS audit (B1) is
> done and recorded. The Fastweb Seven network audit (B2) is waiting on the ISP box being physically installed.
> The DNS architecture itself is **approved for implementation planning — pending B2 and B3**
> ([ADR 0001](docs/adr/0001-dns-architecture.md)).

---

## Purpose

Provide the home LAN (~16 devices: PCs, Smart TVs, phones, iPads, Xbox) with:

- Stable, fast, DNSSEC-validating DNS resolution
- Low-false-positive filtering of ads, trackers, malware and phishing
- Per-device-group policies (conservative for Smart TVs and Xbox)
- Blocklist validation with a protected-domain tripwire before every deployment
- Monitoring, Telegram alerts, storage protection, backups with tested restore
- A custom, responsive, LAN-only web dashboard

The Raspberry Pi is **only a DNS server**. It is not a router, gateway, proxy or part of the normal packet path.

## Architecture (planned for production)

```text
INTERNET ── Fastweb Internet Box Seven (router, gateway, NAT, Wi-Fi)
                     │
                    LAN ── PCs · Smart TVs · phones · iPads · Xbox
                     │
             DNS queries (port 53)
                     ▼
        Raspberry Pi 4 ── Pi-hole v6 (filtering, groups, API)
                              │ 127.0.0.1:5335
                              ▼
                          Unbound (recursion, DNSSEC)

Custom dashboard backend (FastAPI, same process serves the built React SPA)
        ── Pi-hole official API (LAN only)
```

**Not installed yet.** Pi-hole and Unbound have not been installed on the Pi — the whole backend/dashboard was
built and tested offline (Stage A) against a `MockDnsProvider`, precisely so that installing the real DNS
software (Stage C) is the *last* step, not the first, and only happens once every ADR 0001 validation gate
(§7) has passed. See "Why Pi-hole/Unbound aren't installed yet" below.

- Decision and trade-offs: [docs/adr/0001-dns-architecture.md](docs/adr/0001-dns-architecture.md)
- Evidence and decision matrix: [docs/architecture-comparison.md](docs/architecture-comparison.md)

**Open questions that can still change the design** (see ADR 0001 §7–§8, all waiting on the Fastweb Seven — B2):
- How the Fastweb Box Seven hands out DNS servers over IPv4 and IPv6
- Whether its "DNS protetto"/DNS proxy intercepts DNS traffic
- Real-world Pi-hole behaviour for IPv6 clients in MAC-based groups (only testable after install, gate G6)

## Dashboard

A fully custom, LAN-only, dark-first ("Night Ops") web dashboard, served from the same FastAPI process as the
API (no nginx, no separate frontend host — [ADR 0010](docs/adr/0010-frontend-hosting.md)):

- Overview page: a client-side-computed health score (never fabricated — derived only from fields the API
  already returns) broken down into DNS/latency/blocklist-freshness/system/backup components, live system
  gauges (CPU/RAM/temperature/storage), a query-volume area chart, an incident heartbeat strip, most-active
  devices, and a recent-activity summary.
- Devices, Security, System, Alerts and an admin-only query log, with role-based (admin/viewer) data exposure
  enforced server-side, not just hidden client-side.
- A role-filtered ⌘K command palette and quick actions — administrative actions (backup, blocklist update) are
  shown as clearly administrative but are **not** wired to any real mutating endpoint yet; that requires
  separate, explicit approval once the real Pi-hole/Unbound stack exists.
- Cookie-based sessions, CSRF on every unsafe method, a path-aware Content-Security-Policy, no CORS
  (same-origin only), scrypt-hashed passwords, login rate limiting.

Built in two passes on top of A7/A8 (backend + original dashboard): commit `1f0ef32` (redesign) and `7d41eeb`
(the deferred UI items — per-source blocklist freshness, most-active devices, recent activity, theme toggle).
Design/security details: [docs/specs/a7-backend.md](docs/specs/a7-backend.md),
[docs/specs/a8-frontend-dashboard.md](docs/specs/a8-frontend-dashboard.md),
[docs/audits/2026-09-14-a9-security-review.md](docs/audits/2026-09-14-a9-security-review.md).

## Why Pi-hole/Unbound aren't installed yet

CLAUDE.md's own priority order is stability → DNS performance → compatibility → security → filtering quality →
observability → automation → customization — which means proving the *software* works correctly, offline,
before it ever touches the real DNS path. Concretely: ADR 0001 requires gates **G1–G5** to pass before
installation (Phase 5) is authorised at all, and gate **G6** (MAC-based device policy over IPv6) can only be
tested *after* install, before device policies roll out. G1/G2 (the Raspberry Pi's own hardware/OS/resource
baseline) are done — see [the B1 audit](docs/audits/2026-09-14-b1-raspberry-pi-audit.md). G3–G5 depend entirely
on the Fastweb Seven's actual DHCP/DNS/IPv6 behaviour, which cannot be measured until the ISP box is physically
installed and active. Installing Pi-hole/Unbound before that would mean configuring a DNS server for a network
whose real DNS-delivery behaviour is still unknown — exactly the kind of premature, hard-to-undo change CLAUDE.md
§47 and §54 warn against.

## What B2 / B3 / Stage C mean

| Stage | What it is |
|---|---|
| **B1** (done) | Read-only Raspberry Pi hardware/OS/resource audit. Recorded in [docs/audits/2026-09-14-b1-raspberry-pi-audit.md](docs/audits/2026-09-14-b1-raspberry-pi-audit.md). |
| **B2** (waiting) | Read-only Fastweb Seven network audit, once the Box Seven is physically installed: LAN/DHCP behaviour, DNS interception, IPv4/IPv6 DNS delivery (ADR 0001 gates G3–G5). |
| **B3** (waiting on B2) | Re-check ADR 0001 against the B1+B2 findings, resolve `<<AUDIT:...>>` placeholders that depend on them, formally update the ADR's gate table. |
| **Stage C** (not started, not authorised) | Actual Pi-hole v6 + Unbound installation, the real `PiholeV6Provider` implementation (today it's `MockDnsProvider` only), production configuration, systemd units/timers, backup/restore rehearsal on real hardware. |
| **Stage D** (not started, not authorised) | Pilot devices, device-group policy rollout (gate G6), IPv6/DNS-bypass validation, whole-network cutover, soak test. |

## Requirements

| Item | Value |
|---|---|
| Hardware | Raspberry Pi 4, 4 GB RAM, 32 GB microSD (USB 3 SSD migration path reserved, not needed yet — [ADR 0007](docs/adr/0007-storage-strategy.md)), Ethernet |
| OS (confirmed, B1) | Debian GNU/Linux 13 (trixie), kernel 6.18.34+rpt-rpi-v8, ARM64/aarch64, Raspberry Pi OS Lite-style install |
| ISP / router | Fastweb Seven Casa 2.5 Gbps, Internet Box Seven — **not yet physically installed** |
| Access | SSH to the Pi (`michele@home-dns.local`); VS Code Remote SSH recommended |

## Development

Full detail (setup, dashboard auth, curl examples, troubleshooting): [docs/development.md](docs/development.md).
Quick reference:

```bash
make setup                 # once (needs Internet): uv sync --locked + npm ci
make check                 # lint + all tests + validate-config (development) + frontend build — the CI gate
make test                  # Python + frontend tests, offline
make lint                  # ruff, ruff format --check, mypy --strict, tsc

make serve-mock            # dashboard API on 127.0.0.1:8080 with the mock DNS provider
make serve-static          # build the frontend and serve it + the API from one process (matches production)
```

`serve`/`serve-static` refuse to start until at least one admin user exists:

```bash
uv run home-dns auth set-password --username admin --role admin
```

Then open `http://127.0.0.1:8080/` and log in. The dashboard is fully usable against the mock provider — every
screen, chart and role-gated view works exactly as it will on the real Pi, just with synthetic DNS data.

## Roadmap

Revised 2026-09-13, updated as each stage completes. Full detail and exit criteria: [docs/implementation-plan.md](docs/implementation-plan.md).

| Stage | Phases | Touches Pi / network? | Status |
|---|---|---|---|
| Done | Architecture comparison + ADR 0001; interim network snapshot | No | ✅ |
| **A: offline software** | A0 foundations · A1 configuration · A2 blocklist pipeline · A3 filtering logic · A4 storage & maintenance · A5 monitoring · A6 Telegram · A7 backend · A8 dashboard · A9 offline integration rehearsal | **No** | ✅ **All of A0–A9 done** (1132 backend + 130 frontend tests, `make check` green) |
| Dashboard redesign | Night Ops visual/UX redesign on top of A7/A8 (health score, honest admin-action pattern, dark-first theme) | No | ✅ Done — commits `1f0ef32`, `7d41eeb` |
| **B: pre-deployment audits** | B1 Raspberry Pi audit · B2 Fastweb Seven network audit · B3 architecture re-validation | Read-only | ✅ B1 done ([audit](docs/audits/2026-09-14-b1-raspberry-pi-audit.md)) · ⏳ B2 waiting on Fastweb Seven · ⏳ B3 waiting on B2 |
| C: Pi deployment, isolated | C1 Pi-hole + Unbound install · C2 real provider adapter · C3 live pipeline/monitoring/alerts · C4 backend + dashboard · C5 backup/restore + rollback rehearsal | Pi only | ⛔ Not authorised — except C4's repo-side artifacts (systemd unit, deployment docs, tests), which are done offline; see [docs/deployment/raspberry-pi.md](docs/deployment/raspberry-pi.md). Live install on the Pi still awaits explicit authorisation |
| D: network integration | D1 pilot devices · D2 device policies (G6) · D3 IPv6 + bypass · D4 network cutover · D5 soak + final docs | Yes, each change approved | ⛔ Not authorised |

## Repository layout

| Path | Contents |
|---|---|
| `docs/` | Operational documentation (some pages remain intentional placeholders — see below) |
| `docs/adr/` | Architecture Decision Records |
| `docs/audits/` | Raspberry Pi and network audit results (read-only, never change the system) |
| `docs/specs/` | Per-phase design specs (A0–A9) |
| `config/` | Configuration templates: DNS, groups, policies, protected domains, Telegram, monitoring, storage |
| `lists/` | Blocklist and allowlist sources by category |
| `scripts/` | Audit, install, setup, update, blocklist pipeline, monitoring, maintenance, backup, restore, frontend type generation |
| `src/home_dns/` | Python package: core, config, providers, storage, API backend, CLI |
| `dashboard/frontend/` | Dashboard UI (React + Vite, built to static files, served by the backend) |
| `tests/` | DNS, security, compatibility, blocklist, API, dashboard and integration-rehearsal tests |
| `deployment/` | systemd units, reverse-proxy config (native install, no Docker) — `systemd/home-dns-dashboard.service` added (C4); `nginx/` stays empty (ADR 0010) |
| `data/` | Runtime data placeholder. Real data lives on the Pi and is **not** committed |

Deviations from the original layout in `CLAUDE.md` §8:
- `deployment/docker/` is intentionally **omitted**, because ADR 0001 selects a native install (also keeps host ARP/NDP visibility for MAC-based device identity).
- `docs/adr/`, `docs/audits/` and `docs/specs/` were added.
- `src/home_dns/` holds all Python code. The backend is `home_dns.api`, and `dashboard/backend/` and `dashboard/shared/` were removed ([ADR 0002](docs/adr/0002-software-stack.md)).

## Documentation status

Written and current, reflecting the real, built system (not aspirational):
[devices.md](docs/devices.md) · [monitoring.md](docs/monitoring.md) · [telegram-alerts.md](docs/telegram-alerts.md) ·
[maintenance.md](docs/maintenance.md) · [storage.md](docs/storage.md) · [backups.md](docs/backups.md) ·
[restore.md](docs/restore.md) · [security.md](docs/security.md) · [troubleshooting.md](docs/troubleshooting.md) ·
[policies.md](docs/policies.md) · [development.md](docs/development.md) ·
[deployment/raspberry-pi.md](docs/deployment/raspberry-pi.md) (C4 — repo-side artifacts done, live Pi install pending authorisation).

**Intentionally still placeholders** — each depends on facts Stage B2/C haven't produced yet, and writing them
now would mean inventing content (see [docs/troubleshooting.md](docs/troubleshooting.md)'s own note on this):
[installation.md](docs/installation.md) (Stage C) · [dns.md](docs/dns.md) (Stage C) ·
[networking.md](docs/networking.md), [ipv4.md](docs/ipv4.md), [ipv6.md](docs/ipv6.md), [dns-bypass.md](docs/dns-bypass.md) (all need real Fastweb Seven behaviour, B2) ·
[architecture.md](docs/architecture.md) (remaining sections, same dependency).

## Security

- **Never commit secrets.** That includes Telegram tokens, passwords, API keys, SSH keys and session tokens. Use `.env` on the Pi (from `.env.example`, `chmod 600`) or a systemd `EnvironmentFile`.
- **The dashboard and Pi-hole API are LAN-only** and never exposed to the Internet.
- **Explain before changing anything.** Before any change to DNS, DHCP, IPv6, firewall, routing, router or network interfaces, document what changes, why, the risks and how to undo it (CLAUDE.md §47).
- Details: [docs/security.md](docs/security.md); point-in-time review: [docs/audits/2026-09-14-a9-security-review.md](docs/audits/2026-09-14-a9-security-review.md).

## Development workflow

- **Work incrementally:** explain, run a few commands, read the output, then continue (CLAUDE.md §46).
- **Record decisions:** important decisions get an ADR in `docs/adr/`.
- **Commit meaningfully:** only meaningful, reviewed commits. Agent work is reviewed, tested and security-checked before merge (CLAUDE.md §11).
- Details: [docs/development.md](docs/development.md)
