# home-dns

Home DNS security, ad blocking, performance monitoring and a custom LAN-only dashboard, running on a Raspberry Pi 4.

> **Project status: Planning (Phase 1–4).**
> Nothing is installed or deployed. No DNS, DHCP, IPv4, IPv6, firewall, router or production service has been changed.
> The DNS architecture is **approved for implementation planning — pending Raspberry Pi audit and final Fastweb Seven network validation** ([ADR 0001](docs/adr/0001-dns-architecture.md)).

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

## Architecture (planned)

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

Custom dashboard backend ── Pi-hole official API (LAN only)
```

- Decision and trade-offs: [docs/adr/0001-dns-architecture.md](docs/adr/0001-dns-architecture.md)
- Evidence and decision matrix: [docs/architecture-comparison.md](docs/architecture-comparison.md)

**Open questions that can still change the design** (see ADR 0001 §7–§8):
- How the Fastweb Box Seven hands out DNS servers over IPv4 and IPv6
- Whether its "DNS protetto"/DNS proxy intercepts DNS traffic
- Real-world Pi-hole behaviour for IPv6 clients in MAC-based groups

## Requirements

| Item | Value |
|---|---|
| Hardware | Raspberry Pi 4, 4 GB RAM, 32 GB microSD (USB 3 SSD planned), Ethernet |
| OS | Raspberry Pi OS Lite 64-bit (to be confirmed by the Raspberry Pi audit) |
| ISP / router | Fastweb Seven Casa 2.5 Gbps, Internet Box Seven (activation expected week of 2026-09-20) |
| Access | SSH to the Pi; VS Code Remote SSH recommended |

## Roadmap

Revised 2026-09-13: offline software first, Pi and network integration last. Full detail and exit criteria: [docs/implementation-plan.md](docs/implementation-plan.md) (**approved 2026-09-13**).

| Stage | Phases | Touches Pi / network? | Status |
|---|---|---|---|
| Done | Architecture comparison + ADR 0001; interim network snapshot | No | ✅ |
| **A: offline software** | ✅ A0 foundations · ✅ A1 configuration · ✅ A2 blocklist pipeline · ✅ A3 filtering logic · A4 storage & maintenance · A5 monitoring · A6 Telegram · A7 backend · A8 dashboard · A9 offline integration rehearsal | **No** | ✅ A0 · ✅ A1 · ✅ A2 · ✅ A3 · next: A4 (awaiting approval) |
| B: pre-deployment audits | B1 Raspberry Pi audit · B2 Fastweb Seven network audit · B3 architecture re-validation | Read-only | — |
| C: Pi deployment, isolated | C1 Pi-hole + Unbound install · C2 real provider adapter · C3 live pipeline/monitoring/alerts · C4 backend + dashboard · C5 backup/restore + rollback rehearsal | Pi only | ⛔ Not authorised |
| D: network integration | D1 pilot devices · D2 device policies (G6) · D3 IPv6 + bypass · D4 network cutover · D5 soak + final docs | Yes, each change approved | ⛔ Not authorised |

## Repository layout

| Path | Contents |
|---|---|
| `docs/` | Operational documentation (placeholders until each phase) |
| `docs/adr/` | Architecture Decision Records |
| `docs/audits/` | Raspberry Pi and network audit results |
| `config/` | Configuration templates: DNS, groups, policies, protected domains, Telegram, monitoring, storage |
| `lists/` | Blocklist and allowlist sources by category |
| `scripts/` | Audit, install, setup, update, blocklist pipeline, monitoring, maintenance, backup, restore |
| `src/home_dns/` | Python package: core, config, providers, storage, API backend, CLI |
| `dashboard/frontend/` | Dashboard UI (React + Vite, built to static files) |
| `tests/` | DNS, security, compatibility, blocklist, API and dashboard tests |
| `deployment/` | systemd units, reverse-proxy config (if needed) |
| `data/` | Runtime data placeholder. Real data lives on the Pi and is **not** committed |

Deviations from the original layout in `CLAUDE.md` §8:
- `deployment/docker/` is intentionally **omitted**, because ADR 0001 selects a native install.
- `docs/adr/`, `docs/audits/` and `docs/specs/` were added.
- `src/home_dns/` holds all Python code. The backend is `home_dns.api`, and `dashboard/backend/` and `dashboard/shared/` were removed ([ADR 0002](docs/adr/0002-software-stack.md)).

## Installation · Configuration · Dashboard · Telegram · Maintenance · Backups · Troubleshooting

Not yet written. Each is written in its implementation phase:

- [Installation](docs/installation.md) (Phase 5)
- [DNS](docs/dns.md) (Phase 6)
- [Policies](docs/policies.md) (Phase 10)
- [Telegram alerts](docs/telegram-alerts.md) (Phase 13)
- [Monitoring](docs/monitoring.md) (Phase 12)
- [Maintenance](docs/maintenance.md) (Phase 12)
- [Backups](docs/backups.md) and [Restore](docs/restore.md) (Phase 16)
- [Troubleshooting](docs/troubleshooting.md) (ongoing)

## Security

- **Never commit secrets.** That includes Telegram tokens, passwords, API keys, SSH keys and session tokens. Use `.env` on the Pi (from `.env.example`, `chmod 600`) or a systemd `EnvironmentFile`.
- **The dashboard and Pi-hole API are LAN-only** and never exposed to the Internet.
- **Explain before changing anything.** Before any change to DNS, DHCP, IPv6, firewall, routing, router or network interfaces, document what changes, why, the risks and how to undo it (CLAUDE.md §47).
- Details: [docs/security.md](docs/security.md)

## Development workflow

- **Work incrementally:** explain, run a few commands, read the output, then continue (CLAUDE.md §46).
- **Record decisions:** important decisions get an ADR in `docs/adr/`.
- **Commit meaningfully:** only meaningful, reviewed commits. Agent work is reviewed, tested and security-checked before merge (CLAUDE.md §11).
- Details: [docs/development.md](docs/development.md)
