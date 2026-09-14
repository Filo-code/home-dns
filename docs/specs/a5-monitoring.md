# A5 — Monitoring: Design

- **Status:** implemented 2026-09-14
- **Related:** [implementation-plan.md](../implementation-plan.md) · [ADR 0004](../adr/0004-blocklist-pipeline.md) (blocklist outcomes) · [A4 design](a4-storage-maintenance.md) (StorageReport)
- **Constraints:** offline and development only. No Raspberry Pi, network or production changes. No Telegram sending here — that is A6's job.

## 1. Scope

A5 turns raw check results into **debounced incidents** and **structured alert events**. It does
not send anything anywhere: `core.monitoring` is pure decision logic, `storage.monitoring` persists
incident/escalation state to `data_dir` (survives process restarts, since a scheduled check in
C-stage is a fresh CLI invocation each time), and the CLI prints the resulting alert events. A6
consumes those events and actually dispatches to Telegram, per the existing severity catalog in
`config/telegram/alerts.yaml`.

No concrete DNS/Pi-hole/Unbound checks exist yet (they don't exist to check). A5 delivers the
**framework** plus the two checks that already have real data to observe:
- storage state (A4's `StorageReport`);
- blocklist mirror freshness (A2's pipeline `Outcome`), for the escalation the owner specified
  exactly: warning, warning, critical on the 1st/2nd/3rd+ consecutive `kept_previous` run, reset on
  any `activated`/`unchanged` run.

## 2. Incident state machine

`core/monitoring.py`, pure, no I/O:

```text
OK --(problem)--> SUSPECT --(problem, incident_after reached)--> INCIDENT
OK <--(ok, was only SUSPECT)-- SUSPECT
INCIDENT --(ok)--> RECOVERING --(ok, recovered_after reached)--> OK  [fires RECOVERED]
RECOVERING --(problem)--> INCIDENT                                   [relapse, no re-suspect]
```

- **SUSPECT never alerts.** A single bad result is noise until it repeats `incident_after` times —
  this is the flapping guard the plan asked for.
- **INCIDENT alerts exactly once**, on the `SUSPECT → INCIDENT` transition (`TransitionKind.OPENED`).
  Every further bad result while already `INCIDENT` is a no-op transition: this *is* the
  deduplication the plan asked for — no separate dedup layer is needed, because only a state
  *change* produces a signal.
  - An optional **reminder** while still `INCIDENT`: if `IncidentPolicy.cooldown_seconds > 0` and
    that long has passed since the last notification, `TransitionKind.REMINDER` fires once and
    resets the cooldown clock. Default `cooldown_seconds = 0` disables reminders entirely (alert
    once on open, once on recovery — CLAUDE.md §30's exact example).
- **Recovery needs `recovered_after` consecutive good results**, not one — a single good check
  right after a real incident does not immediately clear it (a second flapping guard).
- **A relapse from `RECOVERING` goes straight back to `INCIDENT`**, not `SUSPECT` — it was already a
  confirmed problem, so it does not need to re-earn `SUSPECT` status.

`advance_incident(previous, result, policy, now) -> (Incident, TransitionKind)` is total and
deterministic. Severity and event-name mapping (which of `config/telegram/alerts.yaml`'s catalog
applies) is the **caller's** responsibility, supplied per check — `core.monitoring` never hard-codes
an event catalog, so it stays reusable for any future check.

## 3. Restart budget (retry/backoff, no infinite loops)

`BackoffPolicy` (max_attempts, base/max delay, exponential factor) + `RestartBudget`
(attempts so far, exhausted). `advance_restart_budget` returns whether to retry and the delay
before the next attempt; once `max_attempts` is exceeded, `exhausted=True` is sticky — the caller
stops restarting and raises a CRITICAL "restart budget exhausted" alert instead of looping forever.
A successful recovery calls `reset_restart_budget`.

## 4. Blocklist freshness escalation

Exactly the owner-approved ladder (2026-09-13), implemented as a direct function of a persisted
per-source counter — deliberately *not* run through the generic incident state machine, because
the ladder's own wording ("1st … warning, 2nd … warning, 3rd … critical") is itself the escalation
policy, evaluated fresh on every pipeline run rather than debounced:

| Consecutive `kept_previous` runs | Severity |
|---:|---|
| 1 | warning |
| 2 | warning |
| ≥ 3 | critical |

Any `activated` or `unchanged` outcome resets the counter to 0 (no alert). This never touches
filtering policy, never bypasses the A2 tripwire, and never causes a deployment — it only adds one
more alert to the report `home-dns blocklists update` already prints.

## 5. Persistence

`storage/monitoring.py`, mirroring A4's atomic-write pattern: one small JSON file per check under
`data_dir/monitoring/incidents/<check>.json`, and one per source under
`data_dir/monitoring/blocklist-freshness/<source>.json`. **`data_dir`, never `tmp_dir`** — per the
A4 persistent-state invariant, this state must survive reboot, since a scheduled check in C-stage
is a new process each time and the "3 consecutive runs" count would otherwise reset spuriously.

## 6. Configuration

New schema-owning loader `config/monitoring.py` for `config/monitoring/monitoring.yaml` (same
pattern as A1's filtering config and A4's storage config):

```yaml
incident:
  incident_after: 2        # consecutive bad results before an incident opens
  recovered_after: 1        # consecutive good results before it closes
  cooldown_seconds: 0       # 0 = no repeat reminders while an incident stays open
restart_budget:
  max_attempts: 5
  base_delay_seconds: 1.0
  max_delay_seconds: 300.0
  backoff_factor: 2.0
```

## 7. CLI

`home-dns monitoring status` — read-only, runs the storage check through the incident machinery
and reports current incident/escalation state (dry-run by nature: observing never mutates policy,
but *does* persist the observed incident/counter state, exactly like a real check would).
`home-dns blocklists update` gains one more line of output per source when its freshness counter is
non-zero — no new subcommand needed, since escalation is a property of the existing report.

## 8. What A5 deliberately does not do

- **No Telegram sending.** `core.monitoring` and `storage.monitoring` produce `Alert` objects with
  a severity, event name and message; A6 is the only place that will ever call the Telegram API.
- **No concrete Pi-hole/Unbound/DNS checks.** Nothing to check yet — those arrive with C1.
- **No new alert events invented.** Every event name used here already exists in
  `config/telegram/alerts.yaml`'s catalog (`storage_above_70/80/90`, `blocklist_update_failure`,
  `suspicious_blocklist`, `protected_domain_tripwire_failure`, `service_recovered`,
  `health_check_failure`).
