# ADR 0001: DNS Architecture — Pi-hole v6 + Unbound

| Field | Value |
|---|---|
| **Status** | **Approved for implementation planning — pending Raspberry Pi audit and final Fastweb Seven network validation.** |
| Date proposed | 2026-09-13 |
| Date approved (planning) | 2026-09-13 |
| Decision owner | Project owner |
| Author | Lead architect |
| Supersedes | — |
| Superseded by | — |
| Evidence | [../architecture-comparison.md](../architecture-comparison.md) |

> **This decision is revisable.**
>
> It authorises implementation *planning* only. It does **not** authorise:
> - installing Pi-hole or Unbound
> - changing DNS, DHCP, IPv4, IPv6, firewall or router settings
> - enabling blocklists
> - deploying the dashboard
>
> Installation (Phase 5) may start only after every validation gate in §7 has passed. If any revision trigger in §8 fires, this ADR is reopened (see §9) and the decision is not treated as final.

---

## 1. Context

The project needs a DNS server on a Raspberry Pi 4 (4 GB RAM, 32 GB microSD, Ethernet). It must provide filtering, security, device policies, and a data source for a fully custom LAN-only dashboard. The Pi is **not** a router, gateway or proxy.

Requirements that drive this decision (from `CLAUDE.md`):
- **Priority order:** stability → DNS performance → compatibility → security → filtering quality → observability → automation → customization.
- **Policies:** per-group (DEFAULT, PC, GAMING, MOBILE, SMART-TV, XBOX), and they must follow the device.
- **Dashboard:** fully custom, using the DNS server's **official API**, never its internal databases.
- **Compatibility:** conservative filtering for Smart TVs, Xbox, streaming and social networks.
- **Storage:** minimal microSD writes, ~30-day query retention, future SSD migration.
- **Recovery:** backups with tested restore, rollback on failed updates.

Known environment constraints at decision time:
- **The current LAN is interim** (observed 2026-09-13). The final connection is Fastweb Seven Casa 2.5 Gbps with the **Internet Box Seven**, expected around the week of 2026-09-20.
- **The interim router advertises its own IPv6 DNS server** over stateful DHCPv6 (RA flags M+O), and has native IPv6.
- **Box Seven behaviour is unconfirmed.** Community reports, not official Fastweb documentation, say it may not allow changing the DNS server handed out by DHCP. They also describe a "DNS protetto"/DNS proxy feature that redirects DNS to Fastweb resolvers.
- **The Raspberry Pi has not been audited yet.** OS, architecture, storage health and resources are unknown.

## 2. Decision

The planned architecture is:
- **Pi-hole v6 (FTL)** as the filtering DNS server;
- **Unbound** as a local, validating, recursive resolver behind it;
- a **native install** (no Docker) on Raspberry Pi OS Lite 64-bit.

```text
LAN clients ──DNS :53──▶ Pi-hole FTL (filtering, groups, cache, API, query DB)
                                   │
                                   ▼ 127.0.0.1:5335
                           Unbound (recursion + DNSSEC validation)
                                   │
                                   ▼
                           Root / TLD / authoritative servers

Custom dashboard backend ──HTTP API (LAN only)──▶ Pi-hole FTL /api
```

Versions evaluated: Pi-hole FTL v6.7 / Web v6.6 / Core v6.4.3 (2026-07-06) and Unbound 1.26.0 (2026-08-04). Exact pinned versions are decided at Phase 5.

## 3. Alternatives considered

| Option | Weighted score (/100) | Main reason not chosen now |
|---|---:|---|
| **Pi-hole v6 + Unbound** | **78.0** | — (chosen) |
| Technitium DNS Server v15.4 | 70.4 | Open OutOfMemoryException in the latest release's recursive resolver, reproduced by the maintainer ([#2093](https://github.com/TechnitiumSoftware/DnsServer/issues/2093), linked to memory reports in [#2030](https://github.com/TechnitiumSoftware/DnsServer/issues/2030)). Per-group policy matches by IP/CIDR only. Single-maintainer project. Yearly .NET major upgrades with repeated API breaking changes |
| AdGuard Home v0.107.79 | 61.8 | Cannot give different clients different blocklists ([#8029](https://github.com/adguardteam/adguardhome/issues/8029), open). Forwarder only: no local recursion or DNSSEC validation (`enable_dnssec` only sets the AD/DO bits upstream). No API tokens, so the backend must hold the admin password. Frequent API field renames |

Also considered and rejected for now:
- **AdGuard Home + Unbound.** Adds recursion and validation, but still has no per-group blocklists, and costs two services, the same as Pi-hole + Unbound.
- **Docker deployment of any option.** Adds a layer nothing requires. It also makes it harder to see the host's ARP/NDP tables, which MAC-based device identification needs.

The full matrix, sources and category rankings are in [../architecture-comparison.md](../architecture-comparison.md).

## 4. Reasoning

1. **Stability (priority 1).**
   - Pi-hole FTL and Unbound are mature C daemons with low memory use and a very large installed base on Raspberry Pi.
   - Technitium, the strongest alternative on features, has an unresolved OOM defect in exactly the configuration we would run: recursion + DNSSEC on a Pi.
2. **Per-group policies that follow the device.**
   - Each Pi-hole group can have its own adlists, allow/deny rules and regex rules.
   - Clients can be defined by MAC address. This maps directly to the conservative SMART-TV and XBOX policies.
3. **Least custom backend work for the dashboard.**
   - The official v6 API exposes system metrics (CPU, RAM, temperature) and cache metrics.
   - It also exposes, per query: DNSSEC status, reply time, and the list that caused a block.
   - It includes a MAC-aware network table, and the installed version serves its own OpenAPI spec.
4. **Security.**
   - Unbound validates DNSSEC locally.
   - Unbound `private-address` gives DNS rebinding protection.
   - Pi-hole handles the Firefox canary domain, iCloud Private Relay and DDR by default.
5. **Fallback coverage for unknown router behaviour.**
   - Pi-hole includes DHCPv4 and DHCPv6/RA (via dnsmasq).
   - Unbound can switch from recursion to DoT forwarding.
   - Together these cover the plausible outcomes of the Fastweb Seven audit without changing products.

## 5. Consequences

### Positive
- A single, well-documented API for the dashboard backend.
- Group-based policies without extra plugins.
- Recursion without depending on a third-party public resolver.
- Built-in handling of common DNS-bypass signals (canary domain, Private Relay, DDR).

### Negative / trade-offs (accepted, with required mitigations)

The mitigations below are required, not optional.

| # | Trade-off | Required mitigation |
|---|---|---|
| T1 | **Two services instead of one** (pihole-FTL + unbound): two configs, two update paths, two failure points | Health checks and Telegram alerts cover **both** services independently. Monitoring distinguishes "FTL down" from "Unbound down / SERVFAIL". Restart order is documented |
| T2 | **Unbound configuration is not in Pi-hole Teleporter backups** | The backup system (Phase 16) must explicitly include the Unbound configuration files. The restore test must restore and verify Unbound, not only Pi-hole |
| T3 | **Pi-hole has no native rollback**: `pihole -up` updates all components, and no downgrade is documented | Pin versions. Take a pre-update snapshot: Teleporter export, Pi-hole and Unbound config files, recorded versions. Document and test a rollback procedure before the first update (Phase 12) |
| T4 | **Pi-hole IPv6 / MAC group behaviour is unproven.** [FTL #2390](https://github.com/pi-hole/FTL/issues/2390) reports a MAC-defined client getting the Default group when querying over IPv6. The stale bot closed it; there is no fix | Validate on the final network in Phase 10 (gate G6). Our backend owns device identity; do not assume Pi-hole's. If policies fall back to Default over IPv6 and no acceptable mitigation exists, trigger R4 |
| T5 | No persistent DNS cache across restarts | Use Unbound `prefetch` and `serve-expired`. Restarts are rare and monitored |
| T6 | No encrypted DNS server (DoT/DoH/DoQ) in Pi-hole | Not needed while LAN clients reach the Pi through DHCP. Only matters under trigger R2 |
| T7 | Pi-hole web/API had several High-severity security fixes in 2026 | Keep the API LAN-only. Limit the web/API port to trusted hosts at the Pi firewall. Patch promptly. Alert on new releases |
| T8 | Default retention and write interval (`maxDBdays` 91, `DBinterval` 60 s) do not match project targets | Set ~30-day retention, and a write interval chosen from the Pi audit's storage data (Phase 6/12) |
| T9 | Full recursion sends unencrypted DNS from the Pi to authoritative servers, and ISP DNS interception could affect it | Detect it with DNSSEC/resolution monitoring. Documented fallback profile: Unbound DoT forwarding (subject to gate G5) |

## 6. Main risks

| # | Risk | Likelihood | Impact | Where addressed |
|---|---|---|---|---|
| K1 | Box Seven cannot advertise the Pi as DNS server (DHCPv4 DNS not editable) | Unknown; community reports suggest likely | High: clients do not use the Pi | G3, R1 |
| K2 | Box Seven "DNS protetto"/DNS proxy intercepts port 53, breaking or hijacking Unbound recursion; firmware updates may turn it back on | Unknown | High: SERVFAIL or silent bypass | G4, G5, R3 |
| K3 | Box Seven advertises its own IPv6 DNS, so clients bypass the Pi over IPv6 | Likely (seen on the interim router) | High: filtering and policy bypass | G3, Phase 11 |
| K4 | IPv6 SLAAC temporary addresses break per-device group mapping | Medium | Medium: TVs/Xbox get no conservative policy, or get the strict one by mistake | T4, G6, R4 |
| K5 | Pi hardware or OS not suitable (32-bit OS, failing SD card, throttling) | Unknown | Medium: may need an OS reinstall or SSD before Phase 5 | G1, G2 |
| K6 | Technitium fixes its OOM issue, making the decision a near tie | Possible | Low: needs re-evaluation, not a failure | R5 |

## 7. Validation gates (all must pass before Phase 5 installation)

| Gate | Validation | Pass criterion | Status |
|---|---|---|---|
| G1 | **Raspberry Pi audit** | OS/kernel/architecture known (64-bit expected); storage and filesystem healthy; no throttling or overheating; nothing else listening on port 53; resource baseline recorded | ⏳ Pending (blocked on SSH access) |
| G2 | **Real-world Pi 4 resource/performance baseline** | Idle CPU, RAM, temperature and disk writes measured and documented, for comparison with later measurements (CLAUDE.md §43) | ⏳ Pending |
| G3 | **Fastweb Seven network audit** (after activation) | Documented: LAN subnet; DHCPv4 options and whether they are editable; whether DHCPv4 can be disabled; IPv6 RA flags, RDNSS, DHCPv6 DNS and whether they are editable | ⏳ Pending (Box Seven not active) |
| G4 | **DNS interception / DNS proxy validation** | Known: whether "DNS protetto"/DNS proxy exists; whether it is on by default; whether it intercepts port 53 to external resolvers; whether it can be disabled persistently | ⏳ Pending |
| G5 | **IPv4/IPv6 DNS behaviour validation** | Confirmed how clients learn DNS servers over IPv4 and IPv6 on the Box Seven. Confirmed whether outbound UDP/TCP 53 and 853 reach the Internet unmodified | ⏳ Pending |
| G6 | **IPv6 / MAC group behaviour** (Phase 10, after install) | A MAC-defined client gets its assigned group for both IPv4 and IPv6 queries, or a documented mitigation is proven | ⏳ Pending (post-install; failure triggers R4) |

G1–G5 block installation. G6 can only be tested after installation, so it blocks the rollout of device policies (Phase 10), not Phase 5.

## 8. Revision triggers (reopen this ADR if any occur)

| # | Trigger | Why it matters | Likely direction of re-evaluation |
|---|---|---|---|
| R1 | Box Seven cannot hand out the Pi as DNS **and** its DHCP cannot be disabled | Pi-hole only helps if clients use it. Clients would then need DNS set per device, plain or encrypted | Re-weight the "encrypted DNS server" and "ClientID" criteria, where AdGuard Home and Technitium are stronger. Consider per-device configuration, or a router behind the Box Seven (separate ADR) |
| R2 | Encrypted DNS from clients to the Pi (Android Private DNS, iOS profiles, Windows DoH) becomes a requirement | Pi-hole has no DoT/DoH/DoQ server | Re-score. Consider AdGuard Home, Technitium, or a TLS front end that keeps filtering |
| R3 | Port 53 interception cannot be disabled persistently **and** port 853 is blocked or intercepted | Neither recursion nor the DoT fallback would work reliably | Re-evaluate the upstream design (DoH forwarding) and whether the product choice still holds |
| R4 | G6 fails: IPv6 queries from MAC-defined clients do not get their group, and no acceptable mitigation exists (for example, controlling IPv6 DNS advertisement, or IPv4-only DNS for policy devices) | Per-device policy is a core requirement | Re-evaluate the device identification strategy, then the product choice |
| R5 | Technitium fixes the recursive OOM defect (#2093) in a **stable release before Phase 5 starts** | The comparison becomes a near tie (77.6 vs 78.0 with stability re-scored) | Re-score stability with current evidence. Re-check IP-only group matching against G3/G6 findings |
| R6 | The Pi audit or baseline measurements show Pi-hole + Unbound cannot meet stability or resource needs on this hardware | Priority 1 is stability | Re-evaluate |
| R7 | An unpatched critical security issue in Pi-hole or Unbound, or either project becomes unmaintained | Security and long-term maintainability | Re-evaluate |

## 9. How this decision may be revised

1. When a trigger fires, record the evidence in the relevant audit document under `docs/audits/`.
2. Set this ADR's status to **"Under review"**, with the trigger number and date. Do not delete the original reasoning.
3. Re-run the affected parts of the decision matrix in `docs/architecture-comparison.md` with the new evidence.
4. If the decision changes: write a **new ADR** that supersedes this one (next free number, for example `NNNN-dns-architecture-revision.md`), and set this ADR's status to **"Superseded by NNNN"**.
5. If the decision stands: return this ADR to its previous status and add a dated note to the review log below.
6. No production change may rely on a decision that is "Under review".

No DNS software has been installed, so revising before Phase 5 costs nothing to roll back. After Phase 5, a revision needs a migration plan in the superseding ADR: backup, parallel run on another port or host, cut-over, rollback path.

## 10. Review log

| Date | Event |
|---|---|
| 2026-09-13 | Proposed after a documentation-based comparison of Pi-hole + Unbound, AdGuard Home and Technitium |
| 2026-09-13 | Owner approved for implementation planning, conditional on gates G1–G5. Installation not authorised |

## 11. References

- Evidence and decision matrix: [../architecture-comparison.md](../architecture-comparison.md)
- Pi-hole API: https://docs.pi-hole.net/api/
- Pi-hole group management: https://docs.pi-hole.net/group_management/
- Pi-hole + Unbound guide: https://docs.pi-hole.net/guides/dns/unbound/
- Pi-hole FTL configuration: https://docs.pi-hole.net/ftldns/configfile/
- Pi-hole FTL #2390: https://github.com/pi-hole/FTL/issues/2390
- Unbound configuration: https://unbound.docs.nlnetlabs.nl/en/latest/manpages/unbound.conf.html
- Technitium #2093: https://github.com/TechnitiumSoftware/DnsServer/issues/2093
- Technitium #2030: https://github.com/TechnitiumSoftware/DnsServer/issues/2030
- AdGuard Home #8029: https://github.com/adguardteam/adguardhome/issues/8029
