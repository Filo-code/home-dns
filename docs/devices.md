# Devices

> **Status:** implemented and tested offline against the mock provider (A7/A8). Real-device
> identification (real MACs, real IPv6 behaviour) is validated in Stage C/D.

Device inventory, identification (IP, MAC, hostname), naming, group assignment.

## Known so far

IPv6 device identification is a known weakness (ADR 0001 T4, gate G6): a rotating IPv6 address
maps to a device only once the provider's network table has associated it with a MAC.

## What it does

The backend's device registry (`home_dns.storage.dashboard`) identifies an observed DNS client by
**MAC first, then any known address** — so a daily-rotating IPv6 address still resolves to the
same device once seen under its MAC. Admins can set a custom name and assign a policy group;
viewers see the same list read-only. See [specs/a7-backend.md](specs/a7-backend.md) §4.

## Why it exists

CLAUDE.md §20–21: device inventory, custom names, group assignment, first/last seen, query
totals.

## Dependencies

A7 backend (collector + `DashboardStore`), A8 dashboard (Dispositivi / Dettaglio dispositivo
pages), `config/groups/groups.yaml` for valid group ids.

## Configuration

No dedicated device config file — devices are discovered automatically from provider data.
Available groups come from `config/groups/groups.yaml`.

## Installation

Nothing to install; part of the backend/dashboard. Devices appear only after the collector has
run at least two poll cycles (no backfill on first start) — see
[specs/a7-backend.md](specs/a7-backend.md) §6.

## Operation

Dashboard: open **Dispositivi**; an admin can rename a device or change its group inline.
API: `GET /api/v1/devices`, `PATCH /api/v1/devices/{id}` (admin, CSRF token required).

## Troubleshooting

- **A device appears twice** — an address seen before its MAC was known creates an address-only
  device; once the MAC is seen, it claims that address going forward, but the two historical
  rows are **not** merged automatically (deliberate: merging would silently rewrite historical
  per-device counters). See [specs/a7-backend.md](specs/a7-backend.md) §4.
- **A device never appears** — check the collector actually ran (`metrics.collector_enabled` in
  the app profile) and that at least 5 minutes (one flush interval) have passed.

## Recovery

Device rows live in `data_dir/home-dns.db` (SQLite); restore from the latest backup if the
database is lost or corrupted — see [backups.md](backups.md) / [restore.md](restore.md).

## Rollback

Renaming or regrouping has no dedicated rollback command; set the value back through the
dashboard or `PATCH /api/v1/devices/{id}`.

## Security implications

MAC address and IP history are admin-only, never shown to a viewer
([specs/a7-backend.md](specs/a7-backend.md) §7 — a household's device-and-address history is
sensitive). Custom device names are user input, always rendered as plain text by the dashboard,
never as HTML.
