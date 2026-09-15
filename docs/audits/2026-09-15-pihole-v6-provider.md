# PiholeV6Provider integration — 2026-09-15

> **Scope note:** like the other same-day Stage C files, this is not a passive audit. It records the real `PiholeV6Provider` implementation (`src/home_dns/providers/pihole_v6.py`) and its live verification against the installed Pi-hole v6 lab instance.

## 1. What this is

`PiholeV6Provider` is the real `DnsProvider` implementation for Pi-hole v6, replacing `MockDnsProvider` when `dns_provider.kind: pihole_v6`. `MockDnsProvider` is unchanged and remains the default for development/tests. Everything below was ground-truthed against the live instance (Core 6.4.3 / Web 6.6 / FTL 6.7) via its own served OpenAPI docs and real responses — nothing is assumed from Pi-hole v5 documentation or guessed.

## 2. Endpoints used

| Purpose | Method + path | Auth |
|---|---|---|
| Authenticate | `POST /api/auth` `{"password": ...}` → `{"session": {"valid", "sid", "validity"}}` | password |
| Health | `GET /api/info/ftl` | session |
| Summary | `GET /api/stats/summary` | session |
| Clients | `GET /api/network/devices` | session |
| Per-client blocked count | `GET /api/queries?client_ip=&status=GRAVITY&length=1` (reads `recordsFiltered`) | session |
| Query log | `GET /api/queries?from=&until=&client_ip=&domain=&start=&length=` (offset pagination; reads `recordsFiltered` to know when exhausted) | session |
| Domain lookup | `GET /api/search/{domain}?partial=false` | session |
| Blocklist deploy (small sets only — see §5) | `GET/POST /api/domains/deny/{exact,regex}`, `POST /api/domains:batchDelete` | session |
| System metrics | `GET /api/info/system`, `GET /api/info/sensors` (temperature; optional, degrades to `None`) | session |
| List → source mapping (for `blocked_by`) | `GET /api/lists` (cached once per provider instance) | session |

Session header: `X-FTL-SID: <sid>`. Sessions last `validity` seconds (1800 on this instance); the provider re-authenticates with a 30s safety margin before expiry, and once more on any 401/403 (a single retry, then `AuthenticationError`).

## 3. Authentication and credentials

- Password comes from `SecretSettings.pihole_app_password` (`HOME_DNS_PIHOLE_APP_PASSWORD`), already present in the config schema — no schema change was needed. `PiHoleV6Settings` (`base_url`, `request_timeout_seconds`, `verify_tls`) also needed no changes.
- `bootstrap.py::build_provider()` refuses to construct the provider (`ProviderNotAvailableError`) if the password env var is unset; `evaluate_readiness()` already catches this earlier in `build_runtime()`'s normal startup path.
- The password is never logged, never included in an exception message, and never written to SQLite. `AuthenticationError`'s message names only the fact of rejection, not any credential value.
- The live verification in §7 used Pi-hole's own `cli_pw` (`/etc/pihole/cli_pw`, auto-generated, root-only) rather than the real admin web password — least privilege, and consistent with earlier Stage C lab practice of never handling that password outside the install step itself. `cli_pw` cannot change Pi-hole config but can read data and manage lists, which is everything this provider's read/deploy paths need.

## 4. Error mapping

| Condition | Result |
|---|---|
| Connection refused / DNS failure / TLS error | `ProviderUnavailableError` |
| Timeout | `ProviderUnavailableError` |
| HTTP 401/403 (after one re-auth retry) | `AuthenticationError` (a `ProviderError` subclass) |
| HTTP 429 | `ProviderUnavailableError` |
| HTTP 5xx | `ProviderUnavailableError` |
| Other HTTP 4xx | `ProviderError` |
| Unparseable / unexpected-shape JSON | `MalformedResponseError` |

`health()` is the one method that *catches* `ProviderError` and reports `HealthStatus.DOWN` instead of raising — that is its documented contract. Every other method (`get_summary`, `list_clients`, `query_log`, `system_metrics`, `lookup_domain`, `deploy_blocklist`) raises on failure; none of them fabricate an empty or zero result to paper over an unavailable provider. This is what lets `Collector.poll()` (`collector.py`, unchanged) distinguish "legitimately zero activity" (a normal `DnsSummary`/`QueryPage` with zero counts) from "provider unavailable" (an exception, caught by the collector, which skips the cycle and retries the same window next time — verified live in §7, and by `test_401_on_a_data_call_triggers_one_reauth_and_retry` / `test_timeout_raises_provider_unavailable` / `test_server_error_raises_provider_unavailable` in the unit tests).

## 5. Blocklist deployment — a real, documented gap

`deploy_blocklist()` manages individual domains via `/api/domains/deny/{exact,regex}` (bulk array POST) and `/api/domains:batchDelete`, tagging every entry it owns with a `home-dns:{source_id}` comment so a redeploy can find and replace exactly its own previous entries (matching the `DnsProvider` contract's "replace all entries of one source" semantics, verified in the unit tests). This is correct and efficient for small, validated entry sets — the same scale the shared contract tests exercise (a handful of domains).

It is **not** how the real ~355k-domain HaGeZi sources were loaded during the earlier Stage C lab pass — that used Pi-hole's adlist-URL + `pihole -g` mechanism directly (see `docs/audits/2026-09-15-stage-c-pihole-lab.md` §4). Pushing a full HaGeZi list through this method would mean hundreds of thousands of individual domain records through a REST endpoint meant for exception-list-scale management, not bulk list replacement. A safety cap (`_MAX_DOMAIN_API_ENTRIES = 5000`) makes this an explicit, immediate `ProviderError` instead of a silent multi-hour hammering of gravity — verified by `test_deploy_blocklist_rejects_oversized_entry_sets`.

**Open question, not resolved here:** how the existing A2 pipeline's validated output should reach Pi-hole in production. Two real options exist (register the pipeline's own artifact as an adlist URL Pi-hole can fetch locally, or extend this domain-API path with real batching/rate limits for a size the pipeline would actually produce) — this is a deliberate design decision for the owner, not something to default silently.

## 6. Device identity

`list_clients()` reads `/api/network/devices`, which is the right source (unlike `/api/clients`, which is empty in this lab — see §7) since it already groups multiple IPv4/IPv6 addresses under one real MAC (`hwaddr`), matching the existing `DeviceRegistry`'s MAC-first identity strategy in `collector.py` (unchanged).

One real limitation: Pi-hole synthesizes a non-MAC `hwaddr` like `ip-192.168.1.121` for some entries (loopback, and apparently the Pi's own interface in this instance) rather than leaving it null. The provider detects this (regex-validates against a real 6-octet MAC pattern) and falls back to the client's own address as `client_id` instead of passing through a fake "MAC" — verified by `test_list_clients_maps_network_devices`. This is the honest gap the task anticipated ("if Pi-hole's client API is insufficient for stable identity, document the gap rather than creating a fragile workaround"): for these specific addresses, Pi-hole itself has no real MAC to offer.

## 7. Live verification (real Pi, real traffic)

Run against the installed lab instance (`http://192.168.1.121`), authenticated with `cli_pw`, `source_urls` built from `config/blocklists/sources.yaml` via the existing `load_filtering_config()`:

1. **Authentication + health**: `status=ok`.
2. **Summary**: real counters (`total_queries=1027`, `blocked_queries=60`, `cached_queries=655`, `unique_clients=3`).
3. **Clients**: 3 real devices — `localhost` (127.0.0.1), `pi.hole` (192.168.1.121, itself, synthetic hwaddr → `mac=None`), and the lab Mac with its real MAC (`f6:57:86:e7:42:25`).
4. **Query log**: retrieved real entries (`paypal.com` forwarded, `googlesyndication.com` blocked with `blocked_by="gravity"`, `wikipedia.org` and `example.com` forwarded) after generating them with `dig` directly against the Pi.
5. **System metrics**: real `uptime_seconds=39826`, `cpu_percent≈0.1`, `memory_used_bytes≈128MB/3.98GB`, `temperature_celsius=38.9` (from `/api/info/sensors`, matching the value read directly via SSH at the same time).
6. **Domain lookup**: `googlesyndication.com` → `blocked=True`, `matched_sources=("hagezi-multi-pro",)` — the URL→source-id mapping works end to end against the real gravity match.
7. **Collector, real SQLite**: constructed a real `Collector` + `DashboardStore` in a temp directory. First `poll()` bootstrapped the watermark and correctly read 0 entries (by the collector's existing, unchanged design — no backfill on first start). Four real `dig` queries were then fired at the Pi; the second `poll()` read exactly those 4 entries; `flush()` persisted them. Real result read back from SQLite: 1 minute rollup, device 3 (the Mac's real MAC), `total=4, blocked=1, cached=2, forwarded=1` — the numbers are internally consistent (1+2+1=4) and match the generated traffic exactly.

### Resources (Pi-hole + Unbound + this test, no LAN-wide traffic)

| Metric | Before | After |
|---|---|---|
| RAM | 212 MiB / 3.7 GiB | 206 MiB / 3.7 GiB (noise-level) |
| Temperature | 39.9°C | 38.5°C (noise-level) |
| Disk | 8% | 8% (unchanged) |

No measurable resource impact from read-only API polling at this traffic level. This is a small, manual-scale test, not a production-volume load test (see §8).

## 8. What was not done in this pass

- **Retention/backup/restore/cleanup at length**: not re-exercised beyond the single flush above. The storage layer (`storage/dashboard.py`, `storage/backup.py`, `storage/cleanup.py`) is completely unchanged by this integration — the provider only ever calls the same `DashboardStore.flush()` the existing, already-tested collector path always used, regardless of which `DnsProvider` sits behind it. The live test above proves real Pi-hole data flows correctly into that same, unmodified schema.
- **Realistic/sustained load test**: not performed. Only a handful of manually generated queries were used; do not extrapolate production (~15–16 device) capacity from this.
- **Full shared contract suite (`tests/contract/`) against `PiholeV6Provider`**: not wired up. That suite's fixtures assume full control over a live gravity/domains backend at contract-test scale; the dedicated unit tests (`tests/unit/providers/test_pihole_v6_provider.py`, 31 tests) cover every category Step 15 asked for (auth, session reuse/expiry, 401/403, pagination — including a page spanning multiple underlying HTTP requests, mapping, malformed responses, timeouts, provider-unavailable, empty log, oversized deploys) against a realistic mocked Pi-hole backend instead. Wiring the full contract suite would mean building a second, correctness-complete fake Pi-hole server (gravity matching, regex, redeployment semantics) — a materially larger undertaking than what Step 15 enumerates, and not done here.
- **`PiholeV6Provider` was not wired into the dashboard/API beyond `bootstrap.py`**: the existing FastAPI routes, frontend and API contracts are untouched, since they already only depend on `DnsProvider`, not on which implementation is selected.

## 9. Configuration

To select this provider in a profile:

```yaml
dns_provider:
  kind: pihole_v6
  pihole_v6:
    base_url: http://<pi-address>
```

And set `HOME_DNS_PIHOLE_APP_PASSWORD` in the environment (never in a committed file). `serve` still refuses to start in the `production` environment until Stage C4 — this provider can be exercised today only under `environment: development`, exactly as this lab's live test did.
