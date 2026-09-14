# A7 — Backend: Design

- **Status:** implemented 2026-09-14
- **Related:** [implementation-plan.md](../implementation-plan.md) §A7 · [ADR 0005](../adr/0005-backend-dashboard.md) ·
  [ADR 0002](../adr/0002-software-stack.md) (stack) · [A4 design](a4-storage-maintenance.md) (database file, backups) ·
  [A5 design](a5-monitoring.md) (incidents shown in the alerts view)
- **Owner decisions (this session, 2026-09-14):**
  1. roles **admin + viewer**;
  2. dashboard passwords stored as **scrypt hashes in SQLite**, set through the CLI;
  3. the raw query log is **not copied**: the backend reads it on demand from the provider and
     persists only aggregated rollups;
  4. rollups: poll every **60 s**, batched flush every **5 min**, retention **minute 48 h /
     hour `query_history_days` (30 d) / day 365 d**.
- **Constraints:** offline, development only. Mock provider only. `serve` stays refused in
  production until C4.
- **Official sources checked (2026-09-14):** Pi-hole FTL API specs `queries.yaml`,
  `network.yaml`, `info.yaml`; Pi-hole query-database status table
  (docs.pi-hole.net/database/query-database). Used to shape the provider-neutral models below.

## 1. Scope

A7 is the dashboard's server: authentication, a device registry, historical metrics and a REST
API, all working against `MockDnsProvider`. Everything provider-specific stays behind
`DnsProvider`; `PiHoleV6Provider` must later pass the same contract suite (C2).

## 2. Modules

| Module | Role |
|---|---|
| `core.models` | + `QueryOutcome`, `QueryLogEntry`, `QueryFilter`, `QueryPage`, `SystemMetrics` |
| `core.metrics` (pure) | latency histogram, mergeable `Rollup`, percentiles, bucket boundaries (time-zone aware) |
| `core.auth` (pure) | `Role`, scrypt hash/verify, token generation, login rate limiter |
| `providers.base` | + `query_log()`, `system_metrics()` |
| `providers.mock` | deterministic per-minute query log, IPv6 addresses rotating daily |
| `storage.dashboard` | one migration set on `data_dir/home-dns.db`: users, sessions, devices, device addresses, rollups, collector state |
| `collector` | `DeviceRegistry` (identity resolution: MAC first, then any known IP address) and `Collector` (poll → aggregate in RAM → batched flush); runs as one background thread in the API process |
| `api.context` | `DashboardContext`: store, filtering config, clock, session policy, collector runner |
| `api.app` | factory, security headers, lifespan (collector thread) |
| `api.auth` | login/logout/session routes, session + CSRF + role dependencies |
| `api.views` | dashboard read views and device updates |
| `config.settings` | + `api.cookie_secure`, `api.session_*`, `metrics` section |
| `cli` | + `auth set-password`, `auth list-users` |

`collector` is a new top-level package boundary: it may import `core`, `providers.base` and
`storage`; not `api`, `config`, `cli`, `bootstrap`, `fastapi`, `sqlite3`, `yaml`.

## 3. Provider contract additions

| Operation | Pi-hole v6 source (C2) | Neutral result |
|---|---|---|
| `query_log(filter, *, limit, cursor)` | `GET /api/queries` (`from`, `until`, `client_ip`, `domain`, `cursor`, `length`) | `QueryPage(entries newest-first, next_cursor)` |
| `system_metrics()` | `GET /api/info/system` + `GET /api/info/sensors` | `SystemMetrics(uptime, cpu %, RAM, temperature °C or None, load)` |

- The time window is **half-open `[since, until)`**. The Pi-hole docs do not state whether
  `from`/`until` are inclusive, so the C2 adapter filters client-side; the contract test pins it.
- `QueryOutcome` collapses Pi-hole's 19 statuses: `FORWARDED` (2, 12–14), `CACHED` (3, 17),
  `BLOCKED` (1, 4–11, 15, 16, 18), `OTHER` (0). `blocked_by` carries the source id when known
  (Pi-hole `list_id`), `latency_ms` is `None` when Pi-hole reports a negative `reply.time`.
- **Deferred with reason** (plan listed them under A7): groups/lists/domain-rule CRUD and
  backup export on the provider. A7 stores group assignments in the backend (see
  `config/groups/groups.yaml`), and the configuration view reads the YAML filtering config.
  Pushing assignments into Pi-hole needs the real API and gate G6 → C2/D2. Teleporter export →
  C5. Adding them now would be untestable against anything real.
- **Deviation:** the plan mentioned JSON fixtures shaped like the Pi-hole API. They would have no
  consumer until C2, so the neutral models are shaped after the spec instead and the mapping
  table above is the contract C2 implements.

## 4. Device identity

- Registry rows: `device_id`, `mac` (unique, nullable), `hostname`, `custom_name`, `group_id`
  (default `DEFAULT`), `first_seen`, `last_seen`; plus an address table (`address → device_id`,
  `last_seen`).
- Resolution order for an observed client: **MAC** match → **any known address** match → new
  device. Addresses seen under a MAC are (re)bound to that device, so a rotating IPv6 temporary
  address resolves to the same device as soon as the provider's network table has seen it.
- A query from an address never associated with a MAC creates an address-only device. If that
  address later appears under a MAC, the address is re-bound; the orphan device keeps its
  history (no automatic merge — merging would silently rewrite historical per-device counters).
- `group_id` is validated against the loaded `FilteringConfig` groups on update.

## 5. Metrics model

- Each rollup row: `(resolution, bucket_start, device_id)` → `total`, `blocked`, `cached`,
  `forwarded`, latency histogram (JSON array), blocked-by-source counts (JSON object).
- Latency histogram bins (ms, upper bounds): 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, +∞.
  Histograms merge by addition, so hour/day p50/p95 stay exact **to the bin**; percentiles are
  reported as the bin's upper bound. Exact percentiles would require keeping every sample.
- Derived: `qps = total / bucket seconds`; `block_percentage = blocked / total`;
  `cache_hit_ratio = cached / (cached + forwarded)` (blocked queries never reach cache or upstream,
  so they are excluded).
- Buckets: minute and hour in UTC; **day buckets start at local midnight** of
  `metrics.timezone` (`Europe/Rome`), so a DST day is 23 or 25 h.
- Blocked queries are counted **per blocklist source**, not per category. DNS lists do not label
  individual entries, and a source has several categories (Multi PRO: advertising, tracking,
  telemetry, malware, phishing), so a per-category count would be invented. The API returns
  per-source counts; the dashboard shows each source with its categories from `/config`. A
  blocked query without a known source counts as `unknown`.

## 6. Collector and disk writes

```text
every poll_interval_seconds (60):  provider.list_clients() + query_log([watermark, now))
                                   → resolve devices → merge into RAM minute buckets
every flush_interval_seconds (300): one transaction:
                                   upsert-merge minute, hour and day rows
                                   upsert devices/addresses
                                   store watermark
                                   delete rollups and device addresses older than retention
```

- The watermark is written **in the same transaction** as the buckets. A crash loses no data:
  the next start re-reads the provider log from the last stored watermark. Unflushed RAM is
  simply rebuilt.
- First start (no watermark): begins at the current time; no backfill.
- About 300 commits/day instead of per-query writes. Row counts at 16 devices: roughly 46 k
  minute, 11.5 k hour, 5.8 k day rows at steady state.
- A provider error during a poll is logged and skipped; the watermark does not advance.
- The collector thread starts in the API lifespan when `metrics.collector_enabled` is true and
  stops cleanly (final flush) on shutdown.

## 7. Security model

- **LAN-only bind:** `api.bind_host` must be loopback, private or link-local. Public addresses
  are rejected by the settings schema; the existing readiness advisory for `0.0.0.0`/`::` stays.
- **Passwords:** `hashlib.scrypt`, N=2^17, r=8, p=1 (OWASP minimum), 16-byte salt, parameters
  stored with the hash. Passwords are read by the CLI from an interactive prompt or stdin, never
  from argv. Changing a password revokes that user's sessions.
- **Sessions:** 32-byte random token in cookie `hd_session` (`HttpOnly`, `SameSite=Strict`,
  `Path=/api`, `Secure` = `api.cookie_secure`). Only the SHA-256 of the token is stored. Idle
  timeout 12 h, absolute 7 d (config). `last_seen` is written at most every 5 min per session.
- **CSRF:** per-session token returned by login and `GET /auth/session`, required in
  `X-CSRF-Token` on every unsafe method, compared in constant time. It is stored in clear in the
  sessions table (it must be returned again); on its own it cannot authenticate anything.
- **Rate limiting:** login only — 5 failures per 15 min per client IP and per username → `429`.
  In memory; a restart resets it (a LAN attacker gains 5 more tries per restart). Per-username
  locking lets anyone on the LAN lock an account for 15 minutes, and behind a reverse proxy every
  client shares one IP (TD-011). Other endpoints are authenticated and LAN-only, so no global
  limiter. Unknown usernames are verified against a dummy hash, so timing does not reveal which
  usernames exist.
- **Roles:** `viewer` sees aggregated numbers. `admin` also sees per-domain data (query log,
  top domains, recent activity: this is household browsing history) and may rename devices and
  change groups.
- **Responses:** never include password hashes, session tokens (other than the caller's own CSRF
  token), provider credentials or secrets. Tested by scanning every response body.
- **Headers:** `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, and a restrictive
  `Content-Security-Policy`.
- **Provider credentials:** unchanged from A0 (`HOME_DNS_PIHOLE_APP_PASSWORD`, env only). Using a
  Pi-hole app password rather than the admin password is C2's job.

## 8. REST API (`/api/v1`)

| Method | Path | Role | Content |
|---|---|---|---|
| GET | `/health` | public | unchanged |
| POST | `/auth/login` | public | sets cookie; `{username, role, csrf_token}` |
| POST | `/auth/logout` | any (CSRF) | revokes the session |
| GET | `/auth/session` | any | `{username, role, csrf_token}` |
| GET | `/overview` | viewer | provider health, 24 h totals, block %, cache hit, p50/p95, last-5-min QPS, system metrics, open incidents, last backup, last blocklist activation |
| GET | `/devices` | viewer | registry + 24 h counters |
| GET | `/devices/{id}` | viewer | one device + counters |
| PATCH | `/devices/{id}` | admin (CSRF) | `custom_name`, `group_id` |
| GET | `/devices/{id}/activity` | admin | top domains, top blocked, recent queries (from the provider log, 24 h) |
| GET | `/metrics/history` | viewer | `resolution`, `since`, `until`, optional `device_id` → buckets with derived values |
| GET | `/queries` | admin | proxied provider log with filters and cursor |
| GET | `/alerts` | viewer | A5 incidents that are not `ok` |
| GET | `/config` | viewer | read-only, sanitized: provider/notifier kind, groups, policies, sources, storage thresholds and retention |

Error shape: FastAPI default `{"detail": ...}`. `401` unauthenticated, `403` wrong role or CSRF,
`404` unknown device, `422` validation, `429` login lockout, `503` provider unavailable.

- Device activity scans at most 2 000 provider entries per request and reports `truncated`
  (TD-012).

## 9. Tests

- Provider contract: query-log window semantics, ordering, pagination and cursor stability,
  `system_metrics` ranges — run against the mock now, against Pi-hole in C2.
- Pure: histogram/percentile/merge, DST day buckets, device resolution, scrypt round trip,
  rate limiter.
- Storage: migrations, flush merge, retention pruning, session expiry.
- Collector: poll/flush with a fake clock, crash-then-restart loses nothing, provider error keeps
  the watermark.
- API: every route × role matrix (401/403/200), CSRF on unsafe methods, lockout, cookie flags,
  security headers, no secrets in responses.

## 10. What A7 deliberately does not do

- No raw query-log copy, no backfill, no automatic device merging.
- No provider group/list/rule writes (C2/D2) and no Teleporter export (C5).
- No TLS termination (nginx decision in C4; `cookie_secure` is ready for it).
- No OpenAPI → TypeScript generation yet; A8 generates it from `/api/openapi.json`.
