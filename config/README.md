# config/

Configuration **templates and source-of-truth files** tracked in Git.

> **Nothing here is deployed.** Values that depend on the real environment (addresses, interfaces, retention intervals, cooldowns, list assignments) are intentionally left empty or `null`. They are filled in only after the Raspberry Pi audit and the Fastweb Seven network audit (ADR 0001 gates G1–G5).

| Directory | Purpose | Filled in |
|---|---|---|
| `app/` | Application profiles: `development.yaml` (mock, runnable offline), `production.example.yaml` (placeholders). `production.yaml` is git-ignored | A0 |
| `blocklists/` | Approved blocklist source catalog (`sources.yaml`) | A1 |
| `rules/` | Manual allow / deny / regex rules with metadata and optional expiry | A1 |
| `dns/pihole/` | Pi-hole settings we manage (subset of `pihole.toml`) | Phase 6 |
| `dns/unbound/` | Unbound configuration (not covered by Pi-hole Teleporter; must be backed up) | Phase 6 |
| `groups/` | Device policy groups (no device assignments; those live in backend storage) | A1 |
| `policies/` | Policies: which blocklists a group uses (provisional until A3) | A1 |
| `protected-domains/` | Domains that must never be blocked, one category per file (entries added in A3) | A1 schema / A3 data |
| `telegram/` | Alert routing, severities, anti-spam | Phase 13 |
| `monitoring/` | Health checks and thresholds | Phase 12 |
| `storage/` | Storage thresholds, retention, paths | Phase 12 |

Secrets never go in this directory. Use `.env` (see `.env.example`).
