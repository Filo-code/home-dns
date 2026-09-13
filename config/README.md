# config/

Configuration **templates and source-of-truth files** tracked in Git.

> **Nothing here is deployed.** Values that depend on the real environment (addresses, interfaces, retention intervals, cooldowns, list assignments) are intentionally left empty or `null`. They are filled in only after the Raspberry Pi audit and the Fastweb Seven network audit (ADR 0001 gates G1–G5).

| Directory | Purpose | Filled in |
|---|---|---|
| `dns/pihole/` | Pi-hole settings we manage (subset of `pihole.toml`) | Phase 6 |
| `dns/unbound/` | Unbound configuration (not covered by Pi-hole Teleporter; must be backed up) | Phase 6 |
| `groups/` | Device policy groups | Phase 10 |
| `policies/` | Per-group filtering policy definitions | Phase 10 |
| `protected-domains/` | Domains that must never be blocked (tripwire source) | Phase 8 |
| `telegram/` | Alert routing, severities, anti-spam | Phase 13 |
| `monitoring/` | Health checks and thresholds | Phase 12 |
| `storage/` | Storage thresholds, retention, paths | Phase 12 |

Secrets never go in this directory. Use `.env` (see `.env.example`).
