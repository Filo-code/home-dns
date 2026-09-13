# DNS Architecture Comparison: Pi-hole + Unbound vs AdGuard Home vs Technitium

- **Status:** Research complete. Decision recorded in [ADR 0001](adr/0001-dns-architecture.md): *Approved for implementation planning — pending Raspberry Pi audit and final Fastweb Seven network validation.*
- **Date:** 2026-09-13
- **Scope:** Raspberry Pi 4 (4 GB, microSD) as LAN DNS server behind a Fastweb router; custom dashboard via official API.
- **Network caveat:** the LAN observed on 2026-09-13 is interim. The Fastweb Seven Casa 2.5 Gbps / Internet Box Seven arrives ~week of 2026-09-20. All router-dependent conclusions must be re-validated in the second network audit.

Legend: **FACT** = backed by official documentation, official source code, or release notes (URL given). **ASSESSMENT** = engineering judgment for this project. **UNVERIFIED** = docs silent or source not reachable.

---

## 1. Versions evaluated (FACT)

| Product | Version | Release date | Runtime / language | License |
|---|---|---|---|---|
| Pi-hole | FTL v6.7, Web v6.6, Core v6.4.3 | 2026-07-06 | C (single `pihole-FTL` binary, embedded dnsmasq + web server + Lua) | EUPL-1.2 |
| Unbound | 1.26.0 | 2026-08-04 | C | BSD-3-Clause |
| AdGuard Home | v0.107.79 | 2026-08-18 | Go (single static binary) | GPL-3.0 |
| Technitium DNS Server | v15.4 | 2026-07-11 | C# / .NET 10 runtime | GPL-3.0 |

Sources: https://api.github.com/repos/pi-hole/FTL/releases · https://nlnetlabs.nl/projects/unbound/download/ · https://api.github.com/repos/AdguardTeam/AdGuardHome/releases · https://raw.githubusercontent.com/TechnitiumSoftware/DnsServer/master/CHANGELOG.md

---

## 2. Feature facts by requirement

### 2.1 DNS resolution, cache, DNSSEC

| Capability | Pi-hole + Unbound | AdGuard Home | Technitium |
|---|---|---|---|
| Recursive resolver | Yes (Unbound, official guide on `127.0.0.1:5335`) | **No, forwarder only.** Can forward to a separate Unbound | Yes, built in, QNAME minimisation |
| Forwarding with encrypted upstream | Unbound `forward-tls-upstream` (DoT) | DoH (incl. H3), DoT, DoQ, DNSCrypt | DoH, DoT, DoQ |
| Local DNSSEC validation | Yes (Unbound; FTL `dns.dnssec` optional) | **No.** `enable_dnssec` only "set[s] the AD/DO bits in the upstream requests" (source verified) | Yes, global `dnssecValidation` |
| DNSSEC status per query in API | Yes (`dnssec` field/filter: SECURE/INSECURE/BOGUS…) | `answer_dnssec` (AD flag copied from upstream) | Not in query-log sample (UNVERIFIED) |
| Serve-stale | FTL `dns.cache.optimizer` 3600 s (default on); Unbound `serve-expired` (default off, configurable) | `cache_optimistic` (default off) | On by default (`serveStaleTtl` 3 days) |
| Prefetch | Unbound `prefetch` (guide sets yes) | No dedicated option found | Yes (eligibility/trigger configurable) |
| Persistent cache across restart | No (manual `unbound-control dump_cache/load_cache`, or Redis cachedb) | No (UNVERIFIED; no persistence code found) | **Yes** (`saveCache`) |
| Negative caching | Yes (dnsmasq + Unbound `cache-max-negative-ttl`) | Yes (RFC 2308 via dnsproxy) | Yes (negative TTL 300 s) |
| Rebinding protection | Unbound `private-address` (in official guide) | No dedicated option (UNVERIFIED) | DNS Rebinding Protection app |

Sources: https://docs.pi-hole.net/guides/dns/unbound/ · https://docs.pi-hole.net/ftldns/configfile/ · https://unbound.docs.nlnetlabs.nl/en/latest/manpages/unbound.conf.html · https://github.com/AdguardTeam/AdGuardHome/blob/v0.107.79/internal/dnsforward/config.go · https://github.com/AdguardTeam/AdGuardHome/wiki/Configuration · https://raw.githubusercontent.com/TechnitiumSoftware/DnsServer/master/APIDOCS.md

### 2.2 Encrypted DNS server side (clients → Pi)

| | Pi-hole + Unbound | AdGuard Home | Technitium |
|---|---|---|---|
| DoT / DoH / DoQ server | **None in Pi-hole.** Unbound can serve DoT/DoH, but that path **bypasses Pi-hole filtering** (ASSESSMENT) | DoT, DoH, DoQ, DNSCrypt; Apple `.mobileconfig` generator | DoT, DoH (HTTP/1.1, 2, 3), DoQ |
| Android Private DNS / ClientID | No | Yes (ClientID via SNI or path) | DoT possible; no ClientID concept |

ASSESSMENT: Android Private DNS against the Pi requires a real domain plus a publicly trusted certificate with renewal. It is optional for a home LAN where devices already use the Pi through DHCP.

### 2.3 Filtering and per-device policy

| Capability | Pi-hole + Unbound | AdGuard Home | Technitium |
|---|---|---|---|
| List formats | hosts, domains, ABP `\|\|domain^` subset | Full AdGuard syntax (`$important`, `$badfilter`, `$dnstype`, `$dnsrewrite`, `$client`, `$ctag`) | Core: hosts/domains. Advanced Blocking app: regex + AdBlock lists |
| Regex | Yes (ERE + `;querytype=`, `;invert`, `;reply=`) | Yes | App only |
| CNAME inspection | `dns.CNAMEdeepInspect = true` (default) | Response CNAME/IP/HTTPS hints checked | "CNAME cloaking" blocking |
| **Different blocklists per group** | **Yes** (adlists, allow/deny and regex all assignable to groups) | **No.** Only via `$client`/`$ctag` in custom rules; feature request #8029 open | **Yes**, via Advanced Blocking app (replaces built-in lists) |
| Group matching | IP, CIDR, **MAC**, hostname, interface | IP, CIDR, ClientID (MAC only if AGH is the DHCP server) | **IP / CIDR / listen endpoint only** |
| Per-client upstreams | No (global) | Yes | Via Advanced Forwarding app (not researched in depth) |
| Schedules | No | Blocked-services pause schedule per client | UNVERIFIED |
| Blocked-services catalog (YouTube, Xbox Live…) | No | Yes | No |

Sources: https://docs.pi-hole.net/group_management/ · https://docs.pi-hole.net/regex/pi-hole/ · https://adguard-dns.io/kb/general/dns-filtering-syntax/ · https://adguard-dns.io/kb/adguard-home/clients/ · https://github.com/adguardteam/adguardhome/issues/8029 · https://raw.githubusercontent.com/TechnitiumSoftware/DnsServer/master/Apps/AdvancedBlockingApp/README.md

### 2.4 Client / device identification (critical: native IPv6 LAN)

| | Pi-hole + Unbound | AdGuard Home | Technitium |
|---|---|---|---|
| MAC discovery | Parses ARP and IPv6 neighbour table (`parseARPcache = true`); DHCP lease names | ARP used for names; MAC as identifier **only when AGH runs DHCP** | Only from its own DHCP leases |
| IPv4 + IPv6 of same device | Grouped by MAC in network table | Manual: persistent client with multiple `ids` | Not linked |
| IPv6 temporary (SLAAC) addresses | Known weakness. FTL #2390: a MAC-defined client got the Default group over IPv6 (closed by stale bot as "not planned"; **no fix**) | Known weakness: a new client per rotating address (#4649, #7349) | Each address is a separate client |

Sources: https://raw.githubusercontent.com/pi-hole/FTL/master/src/api/docs/content/specs/clients.yaml · https://github.com/pi-hole/FTL/issues/2390 · https://adguard-dns.io/kb/adguard-home/clients/ · https://github.com/AdguardTeam/AdGuardHome/issues/4649

ASSESSMENT: IPv6 device identity is weak in **all three**. Pi-hole is the only one that natively ties a MAC to IPv4 and IPv6 addresses without running DHCP. The custom backend should own device identity: correlate IP→MAC using the Pi's own neighbour table plus the DNS server's network table. The IPv6 DNS strategy (Phase 11, after the Box Seven audit) decides whether IPv6 policy is reliable at all.

### 2.5 API and custom dashboard fit

| | Pi-hole v6 | AdGuard Home | Technitium |
|---|---|---|---|
| Spec | OpenAPI served at `/api/docs` (matches installed version) | `openapi/openapi.yaml` (81 paths) | `APIDOCS.md` (~8,300 lines); "any action the web console does" |
| Auth | Session SID (`X-FTL-SID`), app passwords, TOTP; SID bound to client IP; `max_sessions` 16; **`app_sudo = false`** by default (app password cannot change config) | Basic auth or session cookie. **No API tokens, no roles.** Backend must hold the admin password | **Non-expiring Bearer tokens**, users/groups with per-section View/Modify/Delete, TOTP, OIDC |
| Real-time push | No (polling) | No (polling) | No (polling) |
| Query log API | `/queries`: filters (domain, client, upstream, type, status, reply, dnssec), cursor pagination; fields include reply time (ms), list_id, upstream, EDE | `/querylog`: `elapsedMs`, `cached`, `upstream`, matched rule + list id, `reason`, `client_proto`, `answer_dnssec` | `/api/logs/query` (**requires Query Logs app**); filters by client IP, protocol, response type, rcode; `responseRtt`; no matched list or reason |
| History / time series | 24 h in memory (10-minute slots); `/history/database` for longer ranges | `/stats` hour/day buckets; retention up to 8760 h | LastHour…LastYear + custom; minute-level limited to 2-hour ranges |
| Clients / groups CRUD | Yes / Yes | Clients + tags / no groups | Via app config JSON (whole document) |
| Blocklist CRUD + update trigger | Yes (`/lists`, `POST /action/gravity`) | Yes (`/filtering/*`) | Yes (settings + `forceUpdateBlockLists`) |
| System metrics (CPU/RAM/temp) | **Yes** (`/info/system`, `/info/sensors`) | No | No (Prometheus DNS counters only) |
| Cache metrics | `/info/metrics` (inserted/evicted/expired, optimized replies) | No hit-ratio endpoint | Dashboard counts Cached vs Recursive |
| Backup API | Teleporter (`GET/POST /teleporter`) | **None** (copy YAML + data dir) | `/api/settings/backup` + `restore`, selective |
| API stability | Spec `version: '6.0'`, no written deprecation policy | Field renames in most releases (e.g. v0.107.79 `enable`→`enabled`) | Breaking changes in v13.0, v14.0–14.2, v15.0, v15.2; old paths kept as obsolete aliases |

Sources: https://docs.pi-hole.net/api/ · https://docs.pi-hole.net/api/auth/ · https://raw.githubusercontent.com/pi-hole/FTL/master/src/api/docs/content/specs/main.yaml · https://raw.githubusercontent.com/pi-hole/FTL/master/test/pihole.toml · https://raw.githubusercontent.com/AdguardTeam/AdGuardHome/master/openapi/openapi.yaml · https://raw.githubusercontent.com/AdguardTeam/AdGuardHome/master/openapi/CHANGELOG.md · https://raw.githubusercontent.com/TechnitiumSoftware/DnsServer/master/APIDOCS.md

ASSESSMENT: all three need a backend that polls and computes p50/p95 latency and long-term rollups itself. Pi-hole saves the most backend work (system metrics, MAC network table, DNSSEC status, list attribution). Technitium has the best auth model. AdGuard Home has the richest per-query fields but the weakest auth and group model.

### 2.6 Storage and microSD writes

| | Pi-hole | AdGuard Home | Technitium |
|---|---|---|---|
| Query store | SQLite `pihole-FTL.db`, WAL | `querylog.json` (JSON lines) | Query Logs (SQLite) app, bounded queue with bulk insert |
| Write cadence | `DBinterval` 60 s (tunable) | Flush every 1000 entries (`size_memory`); stats in bbolt, flushed hourly | Background bulk inserts; stat files hourly/daily |
| Default retention | `maxDBdays` 91 (docs page says 365: contradictory) | Query log 90 days (actually 1–2× because of rotation); stats 1 day | Stats 365 days; query-log app 7 days / 10,000 records |
| RAM-only option | `maxDBdays = 0` (no history after restart) | `file_enabled: false` for query log | `enableInMemoryStats`, `useInMemoryDb` |
| Relocatable to SSD | Path configurable | `dir_path` for query log and stats | Paths configurable |
| Known risk | SQLite "database disk image is malformed" reports (docker-pi-hole #1971) | Open request for RAM-only storage due to SD wear (#5992) | Log queue drops entries on overflow |

ASSESSMENT: all three can meet ~30-day retention with bounded writes. None needs the dashboard to read internal databases.

### 2.7 DNS-bypass mitigations built in

| Mechanism | Pi-hole | AdGuard Home | Technitium |
|---|---|---|---|
| Firefox canary `use-application-dns.net` → NXDOMAIN | Yes (`mozillaCanary = true`, default) | Yes (hard-coded) | Manual blocked zone |
| iCloud Private Relay `mask.icloud.com`, `mask-h2.icloud.com` | Yes (`iCloudPrivateRelay = true`, default) | `icloud_private_relay` blocked service | Manual blocked zone |
| DDR `resolver.arpa` | `designatedResolver = true` (NODATA) | `handle_ddr` | Not researched |
| Bypass detection | None | None | None |

Platform behaviour (FACT, applies to all three):
- Firefox honours the canary only when DoH is on by default, not when the user enabled it: https://support.mozilla.org/en-US/kb/canary-domain-use-application-dnsnet
- Apple recommends NXDOMAIN or NOERROR/no-answer for `mask.icloud.com` and `mask-h2.icloud.com`; users are then prompted: https://developer.apple.com/support/prepare-your-network-for-icloud-private-relay/
- Windows DoH activates only for manually configured servers on the known-DoH list (Cloudflare, Google, Quad9): https://learn.microsoft.com/en-us/windows-server/networking/dns/doh-client-support

ASSESSMENT: bypass *detection* (for example, devices that never query the Pi, or lookups of well-known DoH hostnames) must be built in our monitoring layer whichever product is chosen.

### 2.8 DHCP (possible fallback if the Fastweb router cannot advertise the Pi)

| | Pi-hole | AdGuard Home | Technitium |
|---|---|---|---|
| DHCPv4 | Yes (dnsmasq) | Yes | Yes (multi-scope, reservations) |
| DHCPv6 / RA | Yes (`dhcp.ipv6`, dnsmasq RA) | Yes (`ra_slaac_only`, `ra_allow_slaac`) | UNVERIFIED |

### 2.9 Operations: backup, update, rollback

| | Pi-hole + Unbound | AdGuard Home | Technitium |
|---|---|---|---|
| Update | `pihole -up` updates all components at once; `apt` for Unbound | Built-in updater; backs up YAML + binary to `agh-backup/` | Re-run `install.sh`; major versions require a new .NET runtime |
| Rollback | No native rollback (`pihole checkout` switches branches); Docker date tags | Manual; config `schema_version` migration **blocks downgrade** without the backed-up YAML | Archived binaries at download.technitium.com/dns/archive/; backup before a major upgrade is advised |
| Components | 2 daemons, 2 configs (Teleporter does not include Unbound) | 1 binary (+ Unbound if recursion/validation is wanted) | 1 service + .NET runtime + separately versioned apps |

Sources: https://docs.pi-hole.net/main/update/ · https://github.com/AdguardTeam/AdGuardHome/blob/v0.107.79/internal/updater/updater.go · https://github.com/AdguardTeam/AdGuardHome/blob/v0.107.79/internal/configmigrate/migrator.go · https://raw.githubusercontent.com/TechnitiumSoftware/DnsServer/master/CHANGELOG.md

### 2.10 Stability, security track record, project health (FACT)

- **Technitium v15.4 (latest release) has an open, maintainer-reproduced OutOfMemoryException in the recursive resolver.** Specific domains cause a retry loop, ~150% CPU, and memory at the limit until restart. It was reported on a Raspberry Pi 5 with DNSSEC validation on. Maintainer (2026-08-11): "most likely reason for high memory usage reports" (#2030, 47 comments). No fixed release as of 2026-09-13. https://github.com/TechnitiumSoftware/DnsServer/issues/2093 · https://github.com/TechnitiumSoftware/DnsServer/issues/2030
- Technitium bus factor: top contributor 4,004 commits, next 42.
- Technitium 2026 security fixes: stored XSS and privilege escalation (v15.3), DNS amplification (v15.0).
- Pi-hole 2026 security fixes in v6.6/v6.7: RCE via CivetWeb config injection, session-expiry bypass, API DoS, local privilege escalation. https://pi-hole.net/blog/2026/07/06/pi-hole-ftl-v6-7-web-v6-6-and-core-v6-4-3-released/
- AdGuard Home: security hardening in v0.107.75, .77 and .78. Open memory report #8297 (~300 MB, OOM at 489 MB, status "waiting for data").
- Smart TV / Xbox / YouTube / Twitch: **none of the three publishes official compatibility guidance** (UNVERIFIED for all). Compatibility depends on list choice, blocking mode and the protected-domain tripwire, not on the DNS product.

---

## 3. Weighted decision matrix (ASSESSMENT)

Weights follow the CLAUDE.md §54 priority order and the "custom dashboard is one of the most important criteria" rule. Scores run from 1 (poor) to 5 (excellent) for **this** project. Weighted score = Σ(score × weight) / 5, maximum 100.

| # | Criterion | Weight | Pi-hole + Unbound | AdGuard Home | Technitium |
|---|---|---:|:---:|:---:|:---:|
| 1 | Stability and maturity on Pi 4 (open bugs, runtime, bus factor) | 18 | **4** | 4 | 2 |
| 2 | API and custom-dashboard fit | 14 | **4** | 3 | **4** |
| 3 | DNS performance and caching (recursion, stale, prefetch, persistence) | 12 | 4 | 3 | **5** |
| 4 | Security (local DNSSEC, rebinding, bypass handling, auth, track record) | 12 | **4** | 3 | **4** |
| 5 | Filtering quality and per-group policies | 12 | **4** | 2 | **4** |
| 6 | Compatibility control (TV/Xbox/streaming: per-group leniency, blocking modes) | 10 | **4** | 3 | **4** |
| 7 | Device identification (MAC, IPv4/IPv6 correlation) | 7 | **4** | 2 | 2 |
| 8 | Storage / SD-card write control | 5 | **4** | **4** | 3 |
| 9 | Backup / update / rollback | 5 | 3 | 3 | **4** |
| 10 | Maintenance simplicity | 5 | 3 | **4** | 3 |
| | **Weighted total (/100)** | **100** | **78.0** | **61.8** | **70.4** |

Score rationale:
- **Pi-hole + Unbound**
  - Strengths: most deployed and most mature; C daemons with low RAM use; native MAC grouping and per-group lists; API exposes system, cache, DNSSEC and network data.
  - Loses points for: two daemons, no native rollback, the 2026 web/API CVE cadence, the IPv6 group bug.
- **AdGuard Home**
  - Strengths: simple and stable single binary; best rule syntax and query-log fields.
  - Loses heavily on: no per-group blocklists, no local DNSSEC validation or recursion, no API tokens, frequent API field renames.
- **Technitium**
  - Strengths: richest resolver and security feature set (recursion, persistent cache, serve-stale on by default, encrypted server, token auth); best backup API.
  - Loses heavily on current stability: open OOM bug in the recursive path of the latest release, a single maintainer, yearly .NET major upgrades with repeated API breaks.
  - Group matching is by IP only.

### Sensitivity

- If Technitium's OOM bug is fixed and its stability is re-scored to 4, its total becomes **77.6**, effectively tied with Pi-hole (78.0). The decision is close and hinges on (a) current stability and (b) device identification.
- Removing the device-identification criterion leaves Pi-hole first (78.0 → 72.4 vs Technitium 70.4 → 67.6).
- AdGuard Home stays third unless per-group blocklists are dropped as a requirement.

---

## 4. Category ranking (CLAUDE.md §6)

| Category | Winner | Runner-up | Why (ASSESSMENT) |
|---|---|---|---|
| 1. Best overall | **Pi-hole + Unbound** | Technitium | Highest weighted score; stable today |
| 2. Best customization | Technitium | Pi-hole + Unbound | DNS Apps (C# plugins); every setting via API |
| 3. Best custom web dashboard | **Pi-hole + Unbound** | Technitium | System/cache/DNSSEC/network data via API; less backend work |
| 4. Best API | Technitium | Pi-hole + Unbound | Most complete; non-expiring scoped tokens; backup API |
| 5. Best performance | Technitium (features) | Pi-hole + Unbound | Persistent cache, serve-stale by default. Pi-hole + Unbound uses the least RAM. Real-world cached latency is similar (to be measured) |
| 6. Best stability | **Pi-hole + Unbound** | AdGuard Home | Mature C stack; Technitium has an open OOM bug |
| 7. Best security | Technitium (feature set) | Pi-hole + Unbound | Local DNSSEC, encrypted server, 2FA/token scopes; both have 2026 CVE history |
| 8. Best Smart TV compatibility | **Pi-hole + Unbound** | Technitium | Per-group lenient lists that follow the device by MAC |
| 9. Best Xbox compatibility | **Pi-hole + Unbound** | Technitium | Same reason |
| 10. Best simplicity | AdGuard Home | Technitium | One binary, one config |
| 11. Best long-term extensibility | Technitium | Pi-hole + Unbound | Plugin system; Pi-hole has API + Lua but no plugin model |

---

## 5. Recommendation (ASSESSMENT, pending approval)

**Pi-hole v6 + Unbound, native install on Raspberry Pi OS Lite 64-bit, no Docker.**

Reasons:
1. **Stability first.** Mature C daemons with low memory use. Technitium's latest release has an open, reproduced OOM in exactly the path we would use (recursion + DNSSEC on a Pi).
2. **Per-group policies that follow the device.** DEFAULT / PC / GAMING / MOBILE / SMART-TV / XBOX map directly to Pi-hole groups with separate adlists. AdGuard Home cannot assign lists per client. Technitium can, but only by IP.
3. **Least backend work for the dashboard.** The API already provides CPU/RAM/temperature, cache metrics, per-query DNSSEC status, list attribution and a MAC-aware network table.
4. **Bypass handling on by default:** Firefox canary, iCloud Private Relay, DDR.
5. **Native, not Docker.** No extra layer (CLAUDE.md §54), and direct access to the host ARP/NDP tables that MAC identification needs.

Accepted trade-offs and mitigations:

| Trade-off | Mitigation |
|---|---|
| No persistent cache | Unbound `prefetch` + `serve-expired` (RFC 8767 style); restarts are rare |
| No encrypted DNS server in Pi-hole | Not needed for LAN clients using the Pi via DHCP; revisit only if Android Private DNS against the Pi is wanted |
| Two daemons; Teleporter excludes Unbound | Backup job includes `/etc/unbound/unbound.conf.d/`; health checks cover both services |
| No native rollback | Pin versions; pre-update Teleporter + config snapshot; documented reinstall of the previous tag (Phase 12) |
| Web/API CVE cadence | API LAN-only; Pi firewall limits the web port to trusted hosts; patch promptly; Telegram alert on new release |
| IPv6 group bug (#2390, unfixed) | Test in Phase 10; decide IPv6 DNS strategy after the Box Seven audit; device identity held in the backend |
| Pi-hole defaults (`maxDBdays` 91, `DBinterval` 60 s, `app_sudo` false) | Set ~30-day retention; tune write interval; dedicated app password for the backend (sudo only if required) |
| Full recursion sends plaintext DNS from the Pi to authoritative servers | Acceptable for this privacy scope. If the ISP intercepts port 53 (see §6), switch Unbound to DoT forwarding (Quad9) as a documented fallback profile |

Reconsider Technitium if, by implementation time, both hold: the OOM issue (#2093) is fixed in a stable release with a clean track record, **and** device identification by IP proves sufficient on the final network.

---

## 6. Router-dependent risks (validate on the Fastweb Box Seven)

Community reports only, **not confirmed by official Fastweb documentation** (UNVERIFIED):

1. **DHCP DNS may not be changeable** on the Seven; reportedly only range and lease time are editable.
2. **"DNS protetto" / DNS proxy** is reportedly on by default and **redirects DNS traffic to Fastweb resolvers**. It can reportedly be disabled in the MyFastweb app, but **may re-enable after firmware updates**.
3. **The router advertises its own IPv6 DNS.** This was seen on the interim router via DHCPv6 and is expected, but unconfirmed, on the Seven. Clients can bypass the Pi over IPv6.

Why each matters:
- (1) decides how clients learn the Pi's address: router DHCP option, Pi-hole DHCP with router DHCP disabled, or per-device manual DNS.
- (2) could hijack Unbound's recursive queries. DNSSEC validation would then return SERVFAIL, which monitoring must detect and alert on.
- (3) is the main IPv6 bypass path.

Pi-hole supports every fallback: DHCPv4, DHCPv6/RA, DoT forwarding.

Sources: https://www.fastweb.it/myfastweb/assistenza/guide/seven-configurazioni/ (official page, silent on DNS/DHCP/IPv6) · https://forum.fibra.click/d/70851-fastweb-seven-nuovo-router · https://forum.fibra.click/d/73638-sostituzione-fastweb-seven-con-altro-routermodem

Checklist for the second network audit:
- [ ] Can DHCPv4 DNS be set to the Pi? Can DHCPv4 be disabled?
- [ ] Is "DNS protetto"/DNS proxy present and on by default? Does it intercept port 53 to external IPs?
- [ ] IPv6: RA flags, RDNSS, DHCPv6 DNS, and whether any of these are configurable
- [ ] Does outbound TCP/UDP 853 pass (DoT fallback)?
- [ ] 2.5 GbE LAN port link speed to the main PC. The Pi 4 stays at 1 GbE; DNS traffic is tiny, so this is not a bottleneck
- [ ] Firmware auto-update behaviour, and whether it resets settings

---

## 7. Blocklist availability (FACT, for Phase 8)

HaGeZi lists are maintained and available in Pi-hole-compatible formats:
- **Multi PRO**: ~222k entries. Adblock format: `https://cdn.jsdelivr.net/gh/hagezi/dns-blocklists@latest/adblock/pro.txt`
- **TIF Mini**: ~177k entries. Adblock format: `https://cdn.jsdelivr.net/gh/hagezi/dns-blocklists@latest/adblock/tif.mini.txt`
- A DoH/VPN/proxy bypass list also exists. Candidate for the MOBILE/PC groups only, after testing.

Source: https://github.com/hagezi/dns-blocklists

---

## 8. Research method

- **Product research:** three read-only research agents, one per product, with an identical 19-question brief.
- **Lead re-verification of decisive claims:**
  - AdGuard Home DNSSEC semantics (source at tag v0.107.79)
  - AdGuard Home #8029 status
  - Pi-hole FTL #2390 status
  - Pi-hole `pihole.toml` defaults
  - Technitium #2093 / #2030
- **Router and platform research** (Fastweb, Mozilla, Apple, Microsoft, HaGeZi): done directly by the lead architect.
- **Not yet done:**
  - Raspberry Pi audit (blocked on SSH access)
  - Final network audit (blocked on Box Seven activation)
  - On-device performance measurements
