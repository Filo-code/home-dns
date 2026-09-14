# Monitoring

> **Status:** implemented and tested offline (A5). Real service checks against pihole-FTL and
> unbound come in Stage C, once those services exist; today the framework has two concrete
> checks (storage, blocklist freshness) and is provider-agnostic.

Health checks, metrics, thresholds, retry/backoff/recovery flow, no infinite restart loops.

## Known so far

Two services will need monitoring independently once installed: pihole-FTL and unbound
(ADR 0001 T1). Neither exists yet — nothing here is installed or deployed.

## What it does

`home_dns.core.monitoring` turns a raw check result into a **debounced incident**
(`OK → SUSPECT → INCIDENT`, and `INCIDENT → RECOVERING → OK` on recovery), so one blip doesn't
alert and a real recovery is never missed — see [specs/a5-monitoring.md](specs/a5-monitoring.md).
Two checks exist today: **storage** (from A4's threshold report) and **blocklist freshness**
(consecutive `kept_previous` pipeline runs, escalating warning → warning → critical).

## Why it exists

CLAUDE.md §32: detect → retry → backoff → recover → notify, with no infinite restart loops.

## Dependencies

A4 (`StorageReport`), A2 (pipeline `Outcome`), consumed by A6 (Telegram) and A7/A8 (dashboard
Avvisi page).

## Configuration

`config/monitoring/monitoring.yaml`:

- `incident.incident_after` — consecutive problem checks before entering `INCIDENT`
- `incident.recovered_after` — consecutive OK checks before leaving `INCIDENT`
- `incident.cooldown_seconds` — minimum time between repeat alerts for the same open incident
- `restart_budget` — reserved for Stage C service restarts; unused by today's two checks

## Installation

Nothing to install; part of the `home-dns` package.

## Operation

```bash
home-dns monitoring status              # dry-run: evaluate storage now, print the result
home-dns monitoring status --apply      # persist the incident state for next time
```

Blocklist-freshness state advances automatically as part of `home-dns blocklists update`
(see [blocklists.md](blocklists.md)) — there is no separate command for it.

## Troubleshooting

- **`incident=incident` but storage looks fine right now** — the check reflects the disk usage
  *at the moment it ran*; re-run `monitoring status` to get a fresh reading.
- **No transition even though the underlying state clearly changed** — `incident_after`/
  `recovered_after` require *consecutive* problem/OK results by design; check
  `consecutive_problem`/`consecutive_ok` in the state file (below) to see how close it is.

## Recovery

State lives as plain JSON under `data_dir/monitoring/{incidents,blocklist-freshness}/`. Deleting
a file resets that one check to `OK` — it only loses debounce history, never the underlying data
(storage usage, blocklist artifacts) that produced it.

## Rollback

Not applicable — this state is advisory (it decides when to alert), not authoritative; removing
or restoring a state file only affects debounce continuity, never DNS behaviour.

## Security implications

State files hold only counters and timestamps, no secrets; written with the same atomic-write
(temp file + `fsync` + rename) discipline as blocklist artifacts (A2).
