# ADR 0005: Backend and Dashboard Architecture

| Field | Value |
|---|---|
| **Status** | Accepted |
| Date | 2026-09-14 |
| Decision owner | Project owner (roles, password storage, query-log policy and rollup cadence approved 2026-09-14) |
| Related | [A7 design](../specs/a7-backend.md) · [ADR 0002](0002-software-stack.md) (stack) · [ADR 0007](0007-storage-strategy.md) (storage) · CLAUDE.md §35–§40 |

## Context

The owner wants a custom, LAN-only dashboard (CLAUDE.md §35–§40) showing DNS status, devices,
security and performance, with device renaming and group assignment. It must run 24/7 on a
Raspberry Pi 4 with a microSD card, next to Pi-hole, without becoming a second source of truth
for DNS data and without wearing out the card. Stage A has no Pi and no Pi-hole: everything must
work against `MockDnsProvider`.

## Decision

1. **One backend process** (`home-dns serve`, FastAPI) serves the REST API and runs the metrics
   collector as a background thread. No separate worker service, no message broker, no container.
2. **The DNS provider stays the source of truth for raw queries.** The backend reads the query
   log on demand through `DnsProvider.query_log()` and never copies it. It persists only
   **aggregated rollups** (minute / hour / day, per device) plus the data the provider does not
   own: device names, group assignments, users and sessions.
3. **Batched writes:** the collector polls every 60 s, aggregates in RAM and flushes every 5 min in
   one SQLite transaction that also stores the read watermark. A crash re-reads the provider log
   from the watermark, so nothing is lost or double counted.
4. **Mergeable latency histograms** instead of stored samples; p50/p95 are exact to the bin.
5. **Device identity is owned by the backend:** MAC first, then known addresses; rotating IPv6
   addresses bind to the MAC's device. No automatic merging of historical devices.
6. **Authentication in the backend itself:** local users with roles `admin` and `viewer`,
   scrypt-hashed passwords in SQLite set through the CLI, server-side sessions (only token
   digests stored), `SameSite=Strict` HttpOnly cookie, per-session CSRF token, login rate
   limiting. Domain-level data (query log, top domains) is admin-only.
7. **LAN-only by construction:** the settings schema rejects a public bind address; there is no
   Internet exposure path in the design.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Copy the Pi-hole query log into our own database | Duplicates tens of MB per day on the microSD, and two sources of truth for the same queries |
| Write rollups on every poll | ~1 440 commits/day instead of ~288, for at most 5 minutes less delay on history charts |
| Pi-hole's own web UI and users | Cannot show our device groups or custom views; mixing credentials with the DNS admin password widens its exposure |
| Reverse-proxy authentication only (nginx basic auth) | No roles, no CSRF protection, no logout; still needs TLS to be safe |
| Stateless signed-cookie sessions (JWT) | Cannot be revoked on logout or password change without a server-side deny list, which is a session table again |
| Separate collector service (systemd timer) | A Python start every minute costs more CPU on the Pi than a sleeping thread, and in-RAM aggregation would be impossible |
| Exact percentiles | Requires storing every latency sample |

## Consequences

- History depends on the provider still holding the queries of any period the collector was down.
  Pi-hole keeps far longer than the 5-minute flush interval; only a multi-day backend outage
  can leave a gap.
- Dashboard numbers are up to one flush interval behind real time (`metrics_as_of` shows it).
- Device history split across an address-only device and its later MAC-identified device is not
  merged automatically.
- Login lockout is in memory and per username and IP: anyone on the LAN can lock an account for
  15 minutes, a restart clears lockouts, and a reverse proxy (C4) needs trusted proxy headers
  (TD-011).
- `PiHoleV6Provider` (C2) must implement `query_log` with half-open windows and stable cursors,
  and pass the unchanged contract suite.
