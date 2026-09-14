# Monitoring configuration

`monitoring.yaml` holds the A5 incident/backoff policy — see
[docs/specs/a5-monitoring.md](../../docs/specs/a5-monitoring.md) for the full design.

- `incident.*` — consecutive-result counts and cooldown for the `OK → SUSPECT → INCIDENT →
  RECOVERING → OK` state machine (`src/home_dns/core/monitoring.py`). Suppresses flapping: a
  single bad result is not an incident, a single good result right after one is not a recovery.
- `restart_budget.*` — bounded retry/backoff so a failing check never restarts forever
  (CLAUDE.md §32).

Concrete Pi-hole/Unbound checks (numeric latency/CPU/RAM/temperature thresholds from the
Raspberry Pi resource baseline, ADR 0001 gate G2) are not part of A5 — nothing exists yet to
check. Those arrive with C1, using the same framework this file configures.
