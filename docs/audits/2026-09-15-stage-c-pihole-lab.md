# Stage C lab installation: Pi-hole v6 + Unbound — 2026-09-15

> **Scope note:** unlike the other files in this directory, this is not a passive, read-only audit. It records a real, owner-approved installation and verification performed against the live Raspberry Pi (`home-dns.local`, currently DHCP-assigned `192.168.1.121`). Every step here was explicitly authorized turn-by-turn; see the safety confirmation at the end for exactly what was and was not touched.

## 1. What this is

A controlled **laboratory** installation of Pi-hole v6 and Unbound, both native (no Docker), on the Raspberry Pi that will eventually run the project's real DNS/filtering stack. The Raspberry Pi is **not** the LAN's DNS server. Nothing on the router, DHCP, or any other client was changed. §§1–9 below cover the original Pi-hole-only install; §§11–17 cover the Unbound install performed afterward, in the same lab, under the same constraints.

## 2. Pi-hole installation

Installed via the official installer (`https://install.pi-hole.net`), driven interactively (its `--unattended` flag does not suppress the dialog wizard on a fresh v6 install; this was flagged to the owner before proceeding, who approved driving the real wizard with `expect` and pre-approved every answer).

| Component | Version |
|---|---|
| Core | v6.4.3 |
| Web | v6.6 |
| FTL | v6.7 |

These match the versions ADR 0001 evaluated when the architecture was chosen.

Wizard answers used (all owner-approved in advance):

| Screen | Answer |
|---|---|
| Network interface | default (auto-detected) |
| Upstream DNS | Custom: `192.168.1.254` (temporary bootstrap — the router; **not** a production value, replaced with local Unbound once that is installed and approved) |
| Blocklist | StevenBlack's Unified Hosts List (installer default; replaced in this same session — see §4) |
| Query logging | enabled (default) |
| FTL privacy level | 0 — show everything (default) |
| DHCP | left off. The v6 installer has no DHCP-enabling code path in the wizard at all |

Native config file: `/etc/pihole/pihole.toml` (replaces the old `setupVars.conf` from v5). Confirmed relevant sections:

```
[dns]
upstreams = ["192.168.1.254"]   # marked CHANGED in the file — confirms the wizard answer took effect
dnssec = false
listeningMode = "LOCAL"
queryLogging = true
port = 53

[dhcp]
active = false

[webserver.api]
cli_pw = true
allow_destructive = true
```

Service status: `pihole-FTL` active/enabled, `pihole status` reports FTL listening on port 53 (UDP+TCP, IPv4+IPv6), blocking enabled.

Listening sockets (`ss -lntup`): `pihole-FTL` on `0.0.0.0:53`, `[::]:53` (DNS), `:80`/`:443` (web/API). No other new listeners. `sshd` on `:22` and the pre-existing `avahi-daemon` mDNS listener are unrelated and pre-existed the install.

**`/etc/resolv.conf` is unchanged** — still `nameserver 192.168.1.254` via NetworkManager, exactly as before the install. The Pi-hole installer did not touch the Pi's own system DNS resolution.

## 3. Basic DNS tests

Verified with `dig` against both `127.0.0.1` and the Pi's explicit LAN address `192.168.1.121` (the Pi itself querying its own Pi-hole for these tests; the rest of the LAN continued using the router's existing DNS throughout):

- A record resolution: works (e.g. `google.com` → real IPs).
- AAAA record resolution: works.
- NXDOMAIN handling: works for genuinely nonexistent names.
- Caching: repeat queries return via `CACHE` status in the FTL query log.
- Query-log visibility: confirmed via `pihole.log` and the `/api/queries` endpoint.

## 4. Blocklist swap — and how this differs from the production pipeline

**Do not confuse this lab step with the project's real blocklist pipeline.** The repository already has a full pipeline (`home_dns.core.blocklists`, `pipeline/blocklists.py`, `scripts/blocklists/`) that does validation → mirror/fallback → freshness → dedup → overlap analysis → protected-domain tripwire → retention → rollback, driven from `config/blocklists/sources.yaml`. That pipeline is still the project's source of truth for blocklist *decisions* (which sources, sanity limits, freshness windows). It is unchanged by this lab session.

Pi-hole v6's `PiholeV6Provider.deploy_blocklist()` does not exist yet (see §7), so there is no production-grade path today from the pipeline's validated output into Pi-hole itself. Rather than invent one, this lab used the **safest minimal method available**: it authenticated to Pi-hole's own real REST API (using the auto-generated, config-management-restricted `cli_pw`, not the admin web password) and loaded the exact two canonical source URLs already defined in `config/blocklists/sources.yaml` directly:

- `hagezi-multi-pro`: `https://cdn.jsdelivr.net/gh/hagezi/dns-blocklists@latest/adblock/pro.txt`
- `hagezi-tif-mini`: `https://cdn.jsdelivr.net/gh/hagezi/dns-blocklists@latest/adblock/tif.mini.txt`

No other URL was used or invented. The installer's default StevenBlack list was removed (`DELETE /api/lists/{id}`) since it is not part of the project's blocklist architecture.

**This lab load bypassed the pipeline's protected-domain tripwire.** That tripwire (§19 of the project brief; "ABORT DEPLOYMENT" on a protected-domain hit) only runs inside the A2 pipeline, not inside Pi-hole's own API. Running the protected-domain test script (§6 below) after this direct load was exactly the right caution — and it did surface one apparent conflict (§6), which turned out on investigation not to be a real blocklist match. But in general, **loading blocklists straight into Pi-hole's API, bypassing the pipeline, is not a safe production pattern** — it has no tripwire of its own. Production deployment must go through `PiholeV6Provider.deploy_blocklist()` once implemented, which should call into the existing pipeline rather than the raw Pi-hole list API directly.

Gravity rebuild (`pihole -g`) result:

| List | Parsed entries |
|---|---|
| HaGeZi Multi PRO | 223,220 |
| HaGeZi TIF Mini | 177,847 |
| **Unique after dedup** | **355,727** |

Both counts fall inside the sanity ranges already configured in `config/blocklists/sources.yaml` (Multi PRO 180k–280k; TIF Mini 140k–225k). The measured overlap between the two lists today (223,220 + 177,847 − 355,727 = 45,340) is close to the 45,245 overlap the repo's own research doc (`docs/research/2026-09-13-hagezi-measurements.md`) measured two days earlier — consistent with the day-to-day list drift that same document already characterizes (added/removed ~0.3–2% per update), not a discrepancy.

A second, controlled `pihole -g` run (§8) correctly reported "No changes detected" for both sources with identical counts — confirming update/freshness detection works before any real upstream change occurs.

## 5. A note on how Pi-hole v6 stores ABP-format rules

Early in blocklist testing, direct exact-domain lookups (`pihole -q doubleclick.net`) appeared to fail even for entries that should be blocked. Investigation (reading the real `gravity` table via `sqlite3`) showed FTL stores ABP-style rules (`||sub.domain.tld^`) **verbatim**, wrapper syntax included, in the `gravity.domain` column — it does not pre-strip them into plain domain names at import time. This is not a bug: FTL's query-time matching engine interprets the wrapper syntax correctly (confirmed: `googlesyndication.com` → `0.0.0.0`, and `/api/stats/summary` reports `gravity.domains_being_blocked: 355727` with real blocked-query counts as queries hit gravity). It only means `pihole -q`'s *exact*-match mode won't find a domain unless you know its literal stored form; `--partial` does.

## 6. Blocklist coverage / protected-domain test

Lab-only test script: [`scripts/audit/stage_c_lab_blocklist_test.py`](../../scripts/audit/stage_c_lab_blocklist_test.py). Read-only — DNS queries via `dig` only, no HTTP requests, no site visits. Not part of the production pipeline (see §4).

It tests two sets:

- **Should-block** (11 domains, 4 categories: advertising, trackers, telemetry, malware-phishing) — each confirmed present, verbatim, in the actual downloaded list content on the Pi before being used as a test case.
- **Should-allow** — every domain in the project's canonical `config/protected-domains/*.yaml` (293 entries, 7 categories: banking, gaming, infrastructure, italian, social, streaming, technology), loaded directly from those files, not hand-copied.

To avoid misreporting a domain as "blocked" when it simply has no A record at its bare apex (common for CDN parent zones and infrastructure zones like `root-servers.net`), each apparent block is re-checked against `--control-resolver 192.168.1.254` (the router, unfiltered). Only a domain that resolves on the control resolver but not through Pi-hole counts as a genuine over-block.

Run: `python scripts/audit/stage_c_lab_blocklist_test.py --resolver 192.168.1.121 --control-resolver 192.168.1.254`

Result:

| Outcome | Count |
|---|---|
| `blocked_expected` (should-block domains, correctly blocked) | 11 / 11 |
| `allowed_expected` (protected domains, correctly resolved) | 245 |
| `no_a_record_upstream` (apex has no A record even unfiltered — not a Pi-hole issue) | 47 |
| `unexpected_blocked` (genuine over-block) | 0 |
| `unexpected_allowed` | 0 |
| `dns_error` | 0 |

One domain (`dssott.com`, Disney+ delivery apex) initially looked like an over-block. Direct investigation via Pi-hole's own `/api/queries` showed `status: CACHE`, `reply.type: NODATA`, **`list_id: null`** — i.e. FTL never matched it against gravity at all. The authority section of the raw response carries a real SOA from Disney's own nameserver (`sdns110.ultradns.com`), confirming this is a genuine, authoritative NODATA answer for the bare apex (the domain's CDN answers vary; the control resolver happened to get a populated answer on one attempt). **Conclusion: not a blocklist conflict.** Zero genuine protected-domain over-blocks were found against the 293-entry canonical list.

Full machine-readable results: `stage-c-lab-blocklist-test.json` (generated locally, not committed — regenerate with the command above against the live lab instance).

## 7. Pi-hole v6 REST API — what is now known

Discovered from the live instance's own served OpenAPI spec (`http://127.0.0.1/api/docs/specs/{main,auth,lists}.yaml`), not assumed from v5 docs or memory:

- Auth: `POST /api/auth` with `{"password": "..."}` → `{"session": {"sid": "..."}}`. Session used via the `X-FTL-SID` header.
- `/etc/pihole/cli_pw` is an auto-generated, root-readable-only password specifically for local/CLI automation. Per Pi-hole's own comment in `pihole.toml`: sessions authenticated with it **can** query data and manage lists, but **cannot** change passwords or other config.
- List management: `GET/POST /api/lists`, `DELETE /api/lists/{address}?type=block`.
- Also present in the spec, not yet exercised in this lab: `/api/stats/*`, `/api/history`, `/api/queries` (used read-only above), `/api/dns/blocking`, `/api/domains`, `/api/groups`, `/api/clients`, `/api/info/*`, `/api/logs/*`.

### `PiholeV6Provider`: not implemented yet — here is exactly why

The `DnsProvider` contract (`src/home_dns/providers/base.py`) is now well understood against a real API, and the read side (`health`, `get_summary`, `list_clients`, `lookup_domain`, `query_log`, `system_metrics`) maps cleanly onto the endpoints above. What is still genuinely undecided, and should not be guessed:

1. **Credential delivery.** `PiHoleV6Settings` (`src/home_dns/config/settings.py`) has no credential field today (only `base_url`, `request_timeout_seconds`, `verify_tls`). A real backend cannot authenticate with the root-only `cli_pw` file the way this lab session did over SSH — it needs its own settings-driven secret (env var or secret file), which is a config-schema decision, not something to invent silently mid-implementation.
2. **Session lifecycle.** Sessions last ~30 minutes and are extended by activity. A long-running backend needs a defined re-auth/retry policy; none exists yet.
3. **Error-code mapping.** The real API's error shapes (`{"error": {"key": ..., "message": ...}}`) need mapping onto whatever error model the rest of `home_dns` already uses; not yet reviewed against the existing `MockDnsProvider` error conventions.

Given these are real, unresolved design decisions rather than missing facts, `PiholeV6Provider` was **not** implemented in this pass. `MockDnsProvider` is untouched and the A0–A9 rehearsal remains the only exercised provider path. This is a decision for the owner to make deliberately (likely alongside the credential-storage approach for Stage C/production generally), not something to default silently.

## 8. Resource usage

Measured after the full install + two gravity builds (355,727-domain DB) + the full test-domain pass:

| Metric | Value |
|---|---|
| RAM | 244 MiB used / 3.7 GiB total |
| CPU | ~96% idle, load average 0.13 (1 min) |
| Temperature | 39.4°C |
| Disk | 2.2 GB / 29 GB used (8%) |
| Uptime | 8h05m (since last reboot, unrelated to this session) |

No artificial load/stress test was run, per the owner's instruction — this is real usage from the install, two gravity rebuilds, and the ~304-query test pass.

## 9. What was intentionally not done (as of the Pi-hole-only pass)

- Unbound was **not yet** installed at this point in the session — **superseded, see §11 onward**: it was installed later the same day, under separate explicit approval.
- `PiholeV6Provider` was **not** implemented (see §7). Still true after the Unbound work — see §16.
- No permanent update timers/cron/systemd units were created for blocklist updates; `pihole -g` was run twice, both times manually.
- No stress/load testing was performed.

## 10. Safety confirmation (Pi-hole-only pass)

- Router: **untouched**. No configuration changes of any kind.
- DHCP: **untouched** and confirmed off in Pi-hole itself (`[dhcp] active = false`; the v6 installer has no path to enable it).
- IPv6 router advertisements / RDNSS: **untouched**.
- Other LAN clients: **untouched** — they continue to use the router's existing DNS. Only the Pi itself, queried explicitly by IP, was used for every DNS test in this document.
- `/etc/resolv.conf` on the Pi itself: **unchanged**.
- Firewall: **not touched or configured** (out of scope for this task).
- Unbound: not installed at this point — see §11 onward and the final safety confirmation in §17.

---

## 11. Unbound installation

Installed via the native Debian package (`apt-get install unbound`), no third-party repo, no source build, no Docker.

| Field | Value |
|---|---|
| Package | `unbound` 1.22.0-2+deb13u3 (Debian trixie) |
| Unbound version | 1.22.0 |
| Dependencies pulled in | `libevent-2.1-7t64`, `libhiredis1.1.0` |

Debian's own defaults, inspected before changing anything:

- Root config `/etc/unbound/unbound.conf` just includes `/etc/unbound/unbound.conf.d/*.conf` — the standard Debian layout, left untouched.
- `/etc/unbound/unbound.conf.d/root-auto-trust-anchor-file.conf` (shipped by the package) already configures `auto-trust-anchor-file: "/var/lib/unbound/root.key"` — Debian provides sensible DNSSEC trust-anchor handling out of the box. Not duplicated or changed.
- `/etc/unbound/unbound.conf.d/remote-control.conf` (shipped by the package) enables `unbound-control` on `127.0.0.1`/`::1`:8953 — left at its Debian default, not used in this lab.
- Root hints: no explicit `root-hints:` file is configured; this Unbound build uses its compiled-in IANA root hints, which is normal for a package this recent.
- `unbound-resolvconf.service` (a systemd helper Debian ships to register Unbound into `/etc/resolv.conf` via `resolvconf`) is present and nominally enabled, but its `ConditionFileIsExecutable=/sbin/resolvconf` never fires — `resolvconf` is **not installed** on this host, confirmed by `ls /sbin/resolvconf`. This was checked deliberately before starting the service, given the task's explicit "no DNS loop involving `/etc/resolv.conf`" constraint: it cannot touch `resolv.conf` on this host.

One file was added: `/etc/unbound/unbound.conf.d/pihole-lab.conf` (on the Pi, not in this repository — it is host-local runtime configuration, matching how `pihole.toml` itself is not committed):

```text
server:
    interface: 127.0.0.1@5335
    interface: ::1@5335
    port: 5335
    access-control: 127.0.0.1/32 allow
    access-control: ::1 allow
    do-ip4: yes
    do-ip6: yes
    do-udp: yes
    do-tcp: yes
    prefetch: yes
    hide-identity: yes
    hide-version: yes
    qname-minimisation: yes
    harden-glue: yes
    harden-dnssec-stripped: yes
    use-caps-for-id: no
```

Every directive was cross-checked against `/usr/share/doc/unbound/examples/unbound.conf`, the reference example shipped by this exact package — nothing here was invented. DNSSEC validation relies entirely on the Debian-provided `root-auto-trust-anchor-file.conf`; no second, redundant trust-anchor directive was added.

`sudo unbound-checkconf` → `no errors in /etc/unbound/unbound.conf`, run before the service was ever started.

Note: the very first `systemctl start` attempt (before this config file existed) failed — Debian's stock config, absent any `interface:` override, still defaults to port 53 on loopback, which collided with `pihole-FTL` already bound there. This is exactly why the explicit `port: 5335` / `interface: ...@5335` override above is necessary; it was not a surprise once the log was read (`can't bind socket: Address already in use for ::1 port 53`), and nothing was force-killed or overwritten to work around it — the real fix was adding the correct config.

Service: `unbound.service`, enabled, `active (running)`.

## 12. Listener isolation (Unbound)

`ss -lntup` after starting Unbound:

```
udp   127.0.0.1:5335   unbound
udp       [::1]:5335   unbound
tcp   127.0.0.1:5335   unbound  (LISTEN)
tcp       [::1]:5335   unbound  (LISTEN)
```

No `0.0.0.0:5335`. No `[::]:5335`. No LAN-address:5335. Confirmed both by listener inspection and by an explicit connection attempt from the Pi itself (§14).

## 13. Direct Unbound tests (bypassing Pi-hole, `@127.0.0.1 -p 5335`)

| Test | Result |
|---|---|
| A (`example.com`) | `172.66.147.243`, `104.20.23.154` — NOERROR, 155 ms cold |
| AAAA (`example.com`) | two `2606:4700:10::...` addresses — NOERROR, 11 ms |
| NXDOMAIN (nonexistent name) | `status: NXDOMAIN`, SOA in authority — correct |
| Repeat query / cache (`wikipedia.org`) | first 0 ms, second 3 ms — both fast; NS/TLD delegation was likely already warm from earlier tests, so this is not a dramatic cold-vs-warm contrast, but both are consistent with a local resolver, not a WAN round trip |
| DNSSEC-validating (`cloudflare.com`, `+dnssec`) | `flags: qr rd ra ad` — **AD bit set**, RRSIG returned. Real, measured validation — not assumed. |
| DNSSEC bogus/failure (`dnssec-failed.org`, `+dnssec`) | `status: SERVFAIL`, no answer, no AD — Unbound actively **rejected** an invalid signature chain rather than passing it through |

`dnssec-failed.org` is Verisign/Comcast's long-standing, widely used public test domain for exactly this purpose (intentionally broken DNSSEC) — not a live or malicious site, DNS-only test.

## 14. LAN exposure test

From the Pi itself:

| Target | Result |
|---|---|
| `127.0.0.1:5335` | resolves normally |
| `192.168.1.121:5335` (the Pi's own LAN address) via `dig` | `connection refused` / `no servers could be reached` |
| `192.168.1.121:5335` via raw TCP connect (`/dev/tcp`) | `Connection refused` |

Confirms Unbound is not reachable on the LAN interface, from the LAN interface, consistent with the listener inspection in §12.

## 15. Pi-hole → Unbound switch

Pi-hole's config API (`PATCH /api/config`) is real and documented (ground-truthed from the live instance's own OpenAPI spec, `config.yaml`), but the `cli_pw`-authenticated session used throughout this lab is **deliberately restricted from changing config** — confirmed by a real `403 forbidden` / `"The current CLI session is not allowed to modify Pi-hole config settings"` response, matching Pi-hole's own documented `cli_pw` restriction (query + list-management only). Using the actual admin web password to bypass this was avoided on purpose — it was never captured or reused, per the earlier instruction to treat it as fully confidential.

Instead, the change was made through Pi-hole v6's other real, supported mechanism: `/etc/pihole/pihole.toml` is natively human/script-editable, and FTL re-reads it on restart. A backup (`pihole.toml.pre-unbound.bak`, host-local, not in this repo) was taken before the one-line change:

```diff
- upstreams = ["192.168.1.254"]
+ upstreams = ["127.0.0.1#5335"]
```

`sudo systemctl restart pihole-FTL` was then required (the only service that needed restarting — Pi-hole's web/API run inside the same FTL process, so nothing else was touched). The restart took its full ~60 s `TimeoutStopUSec` to complete: the old FTL process did not exit promptly on SIGTERM, so systemd's own configured timeout ultimately force-completed the restart — the new FTL process (fresh PID) then came up immediately and healthy. Nothing was manually killed or force-restarted; the outcome was systemd's normal, configured behavior.

Confirmed via `GET /api/stats/upstreams` immediately after: a fresh query counted against `127.0.0.1:5335`, not `192.168.1.254` (the router's 300-query count is historical/lifetime and stopped incrementing).

`/etc/resolv.conf` was **not** touched, per the task's own instruction — the Pi's OS-level resolver continues to use the router for its own bootstrap needs, which is fine and does not create a loop (the OS resolver and Pi-hole's upstream are independent).

## 16. Full chain test (client → Pi-hole :53 → Unbound :5335 → Internet)

| Test | Result |
|---|---|
| A | resolves correctly |
| AAAA | resolves correctly |
| NXDOMAIN | `status: NXDOMAIN`, correct |
| Blocked domain (`googlesyndication.com`, HaGeZi) | `0.0.0.0` — still blocked, unaffected by the upstream change |
| Protected domain (`paypal.com`) | resolves normally |
| Repeat query / cache | 0 ms then 3 ms |
| DNSSEC bogus domain through Pi-hole (`dnssec-failed.org`) | `status: SERVFAIL` — **the protection propagates end-to-end through Pi-hole**, even though... |
| DNSSEC-valid domain through Pi-hole (`cloudflare.com`, `+dnssec`) | `flags: qr rd ra` — **no AD bit**. Pi-hole's own `pihole.toml` has `dnssec = false`, so FTL does not relay/set the AD bit toward the client even when its upstream (Unbound) validated the answer. This was measured, not assumed, and is the concrete meaning of "don't duplicate DNSSEC responsibilities": validation happens once, in Unbound, and it does enforce rejection (SERVFAIL) on failure; the AD-bit visibility to LAN clients is a separate, cosmetic setting that was deliberately left as-is rather than changed unrequested. |

Confirms Pi-hole is genuinely forwarding to Unbound (§15's upstream-count evidence) rather than silently falling back to the router.

## 17. Resource comparison — before vs after Unbound

| Metric | Before (Pi-hole only) | After (+ Unbound, two full test passes) |
| --- | --- | --- |
| RAM used | 206 MiB / 3.7 GiB | 212 MiB / 3.7 GiB (Unbound itself: 18 MiB RSS) |
| CPU | idle, load avg ~0.00 | idle, load avg 0.07 |
| Temperature | 40.9°C | 39.4°C (noise-level; not a meaningful drop) |
| Disk | 2.2 GB / 29 GB (8%) | unchanged |
| DNS latency (cold) | n/a (no Unbound) | 155 ms first A lookup via Unbound direct |
| DNS latency (cached) | n/a | 0–3 ms |

On a 4 GB Pi, an extra ~18 MiB RSS process and near-zero measured CPU/load delta is comfortably within headroom — there is no resource pressure from adding Unbound at this query volume. This reflects the actual lab's light, manual query load, not a production-scale LAN (~15–16 devices); a follow-up measurement under real LAN volume is still warranted before the eventual production rollout, not assumed from this lab pass.

## 18. Pi-hole verification (post-switch)

- FTL: `active (running)`, `pihole status` reports listening on 53 (UDP/TCP, v4+v6), blocking enabled.
- Query logging: still `queryLogging = true`.
- Blocklists: both lists still present and unchanged — `hagezi-multi-pro` 223,220 entries, `hagezi-tif-mini` 177,847 entries, `domains_being_blocked: 355727` (identical to before the Unbound work). Blocklist policy was not touched.
- No unexpected fallback upstream: `/api/stats/upstreams` shows new queries going to `127.0.0.1:5335`.

## 19. Repository integration

- `PiholeV6Provider` was **not** implemented in this pass either — the same open questions from §7 (credential delivery, session lifecycle, error mapping) still apply, and adding an Unbound-backed upstream doesn't change any of them.
- No firewall rules added (out of scope, as instructed).
- No production deployment automation added.
- No push to GitHub performed.
- Full `make check` (ruff, ruff format, mypy, pytest, frontend vitest, `validate-config`, `check-types`, `build-web`) run after this documentation update — all green. No `src/` or `tests/` code was touched by the Unbound work, so this mainly re-confirms nothing regressed.

## 20. Safety confirmation (final, covering both passes)

- Router: **untouched** throughout both the Pi-hole and Unbound work.
- DHCP: **untouched**; Pi-hole DHCP confirmed off (`[dhcp] active = false`).
- IPv6 router advertisements / RDNSS / DHCPv6: **untouched**.
- Other LAN clients: **untouched** — every test in both passes targeted the Pi explicitly by IP or `127.0.0.1`/`::1`; the rest of the LAN continues using the router's existing DNS.
- `/etc/resolv.conf` on the Pi: **unchanged** (still points at the router).
- Unbound: confirmed **localhost-only** (`127.0.0.1:5335`, `::1:5335`), verified by both listener inspection and an explicit refused-connection test from the LAN address.
- Firewall: **not added** (out of scope for this task, as instructed).
- Docker: **not installed** — Unbound and Pi-hole are both native Debian packages.
- No production hardening, no production timers, no LAN-wide rollout, no Fastweb Seven integration.
- **The LAN still uses its existing DNS.** This remains a controlled laboratory installation only.
