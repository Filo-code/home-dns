# ADR 0009: Filtering Policy, Protected Domains and Policy Engine

| Field | Value |
|---|---|
| **Status** | Accepted (Light/Normal sanity limits pending owner approval) |
| Date | 2026-09-14 |
| Decision owner | Project owner (A3 scope and constraints, 2026-09-14) |
| Related | [ADR 0003](0003-configuration-model.md) · [ADR 0004](0004-blocklist-pipeline.md) · [design](../specs/a3-filtering-policy.md) · [evaluation](../research/2026-09-14-a3-policy-evaluation.md) |

## Context

After A2 the pipeline could validate lists, but it could not activate anything, and it did not answer three questions:
- which lists apply to which device group;
- which domains must never be blocked;
- why a given domain is blocked for a given device.

Hard requirements (CLAUDE.md §19–§26, owner decisions):
- **Services to keep working:** streaming, Xbox, social networks, YouTube/`googlevideo.com`, Twitch and Italian banking/public services.
- **Protection level:** conservative but meaningful for Smart TVs and Xbox.
- **Engine independence:** no coupling to a specific DNS server.

## Decision

1. **Policy engine** (`core.policy`, pure): precedence protected → allow rule → allow regex → deny rule → deny regex → group's blocklists → default allow. This mirrors Pi-hole v6, so the C2 adapter translates the model instead of re-implementing it.
2. **Protected domains:** 293 entries in 7 category files (italian, banking, technology, gaming, streaming, social, infrastructure), each with a reason and an evidence source. Three tiers:
   - **subtree** only for single-tenant namespaces with no listed names inside, across 8 real HaGeZi lists;
   - **exact** for apexes and essential hosts where upstream lists legitimately block telemetry subdomains;
   - **exact apex guards** for multi-tenant platforms, which never protect tenants.
3. **Policies:**

   | Groups | Policy | Lists |
   |---|---|---|
   | DEFAULT, PC, MOBILE | `standard` | Multi PRO + TIF Mini |
   | GAMING | `gaming` | Multi NORMAL + TIF Mini |
   | SMART-TV | `smart-tv` | Multi LIGHT + TIF Mini |
   | XBOX | `console` | Multi LIGHT + TIF Mini |

4. **Catalog additions:** HaGeZi Multi LIGHT and Multi NORMAL, requested for evaluation by the owner in A3. Their sanity limits are measured and proposed, not configured.
5. **Regex rules** are restricted to a portable POSIX-ERE subset (`core.regex`). Inside it, Python and POSIX engines agree on whether a pattern matches.
6. **Italian filtering layer:** designed, not enabled.
   - Candidates: HaGeZi Fake, Pop-Up Ads, Gambling mini, NSFW; the ADM Italian gambling list; manual deny rules from verified CERT-AgID reports.
   - Each needs an owner decision.
   - DNS limitations are documented; DNS cannot stop JavaScript pop-ups, tabs or redirects executed by a legitimate domain.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Normal for SMART-TV/XBOX | Blocks Prime Video ad-roll hosts and more title/console endpoints than Light, for little extra benefit on TV/console traffic |
| TIF Mini only for SMART-TV/XBOX (previous provisional policy) | Rejected by the owner: "conservative" must still block ads and trackers |
| Subtree protection for every brand apex (e.g. `xboxlive.com`, `fbcdn.net`, `tiktokv.com`) | Would trip the tripwire on legitimate telemetry blocks and make every list undeployable |
| Subtree protection for CDNs/clouds (`cloudfront.net`, `blob.core.windows.net`, …) | Would allowlist phishing and malware hosted by tenants |
| Protecting public DoH resolvers (`dns.google`, `cloudflare-dns.com`) | Would pre-empt the IPv6/DNS-bypass strategy (D3), which may intentionally block them for some groups |
| Hand-written allowlists per service instead of protected domains | Would not feed the deployment tripwire; protected domains enforce at deploy time and at query time |

## Consequences

- **Activation becomes possible in development.** The tripwire has real data, and all 4 active sources pass with 0 hits. Production activation is still C3.
- **Protected domains are enforced at three independent layers:**
  - config validation (deny rules and regexes);
  - the deployment tripwire (A2);
  - query-time precedence (policy engine, and later Pi-hole allowlist entries).
- **Device testing required.** Some protected entries are verified by DNS only (pure video/backend domains), and Prime Video `api.*.aiv-delivery.net` is listed even by Light. Both must be tested on real devices in Stage C/D.
- **Easy refinement.** Changing a group's lists, adding a group-specific exception with `expires_at`, or adding a protected domain is a configuration change. `home-dns policy explain` shows the effect.
