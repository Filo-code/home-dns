# A3 — Filtering Policy: Design

- **Status:** implemented 2026-09-14
- **Related:** [ADR 0003](../adr/0003-configuration-model.md) · [ADR 0004](../adr/0004-blocklist-pipeline.md) · [ADR 0009](../adr/0009-filtering-policy.md) · [evaluation report](../research/2026-09-14-a3-policy-evaluation.md)
- **Constraints:** offline and development only. No Raspberry Pi, router, network or production changes. Real list downloads go to the scratch workflow only; nothing is activated.

## 1. Scope

| In scope | Out of scope |
|---|---|
| Verified protected-domain set (Italian services, banks and payments, big tech, gaming, streaming, social, infrastructure) | Adding new remote lists beyond HaGeZi Light/Normal (Italian layer candidates need an owner decision) |
| Concrete policy per group (6 groups, unchanged) | Device-to-group assignment (A7) |
| HaGeZi Light vs Normal evaluation for SMART-TV / XBOX | Real-device testing (Stage C/D) |
| Policy engine: "for group G, is domain D blocked, allowed or protected, and why?" | Pi-hole translation (C2) |
| Portable POSIX-ERE regex subset validator | Query-type regex extensions (`;querytype=`) |
| Italian filtering layer design + honest DNS limitations | JavaScript pop-up / tab blocking (impossible at DNS level) |
| Compatibility regression catalog and tests | Blocklist sanity limits for Light/Normal (measured and proposed, not configured) |

## 2. Architecture

```text
config (YAML) ──► config.filtering loader ──► core.filtering.FilteringConfig
                                                   │
blocklist artifacts (A2 store / fixtures) ─────────┤
                                                   ▼
                                     core.policy.PolicyEngine        (pure, provider-neutral)
                                     decide(group, domain) -> Decision(verdict, reason, matches)
                                                   │
                         ┌─────────────────────────┼─────────────────────────┐
                         ▼                         ▼                         ▼
               CLI `policy explain`       tests / regression        future PiHoleV6Provider
                                                                     (C2 translates the same model)
```

- **`core.policy` is pure.** No I/O, no config loading, no provider imports. The architecture test enforces this.
- **`core.regex`** holds the portable-subset validator, used by `RegexRule`.
- **Provider neutrality.** Groups map to Pi-hole groups, policies to adlists per group, manual rules to domain entries with groups, and protected domains to allowlist entries for all groups. That translation is C2 work; the policy layer never changes for it.

## 3. Decision precedence

Evaluated top to bottom for one group and one normalized domain. The first match wins.

| # | Layer | Verdict | Pi-hole v6 equivalent |
|---|---|---|---|
| 1 | Protected domain (exact, or subtree when `include_subdomains`) | **allowed** (`protected`) | allowlist entry for all groups |
| 2 | Active manual allow rule (exact / subtree) | allowed (`allow_rule`) | exact allowlist |
| 3 | Active regex allow rule | allowed (`allow_regex`) | regex allowlist |
| 4 | Active manual deny rule | blocked (`deny_rule`) | exact denylist |
| 5 | Active regex deny rule | blocked (`deny_regex`) | regex denylist |
| 6 | Blocklist of a source used by the group's policy (entries block subdomains when rendered `\|\|domain^`) | blocked (`blocklist`) | gravity |
| 7 | Nothing matched | allowed (`default`) | — |

Notes:
- **Expired rules are ignored.** The clock is injected.
- **Protected always wins.** Config validation already forbids deny rules and deny regexes that touch protected domains, and the A2 tripwire forbids lists that contain them. The engine's precedence is the third, independent layer.

## 4. Protected-domain strategy

The goal is to prevent accidental blocking of critical services **without** protecting names that are legitimately blocked, and without hiding malicious tenants on shared platforms.

| Tier | `include_subdomains` | Used for | Rule |
|---|---|---|---|
| **Subtree** | `true` | Single-tenant namespaces used only by one service (e.g. `googlevideo.com`, `nflxvideo.net`, `ytimg.com`, `windowsupdate.com`, `spid.gov.it`) | Allowed only if **no** evaluated HaGeZi list (Light, Normal, Pro, TIF Mini, Pop-up, Fake, Gambling mini, NSFW) contains any name inside it |
| **Exact** | `false` | Brand apexes, login/API/store hosts, and namespaces whose telemetry subdomains are legitimately blocked (e.g. `xboxlive.com` + `xsts.auth.xboxlive.com`, where `beacons.xboxlive.com` stays blockable) | Catches an exact block **and** any list wildcard that covers it (`\|\|parent^`) |
| **Apex guard** | `false` | Multi-tenant platforms (`cloudfront.net`, `akamaized.net`, `azureedge.net`, `blob.core.windows.net`, `amazonaws.com`, `googleusercontent.com`, …) | Only catches a catastrophic "block the whole platform" rule; **never** protects tenants, where phishing is often hosted |

Verification recorded per entry (`source` field + evaluation report):
1. **Existence:** DNS answer for every protected name (Cloudflare DoH JSON, 2026-09-14); NXDOMAIN candidates were dropped.
2. **Ownership**, at one of these levels:
   - official documentation: Apple 101555, Microsoft Windows Update, Microsoft Learn Xbox authentication;
   - the official site served on the domain with the brand title;
   - the domain referenced by the official site;
   - a namespace reserved to Italian public administration (`*.gov.it`);
   - DNS-only for unobservable video/backend domains, flagged in the report.
3. **Gate compatibility:** 0 tripwire hits against the 8 real HaGeZi lists. Subtree candidates with any listed name inside were demoted to exact plus explicit essential hosts.

## 5. Group policies

| Group | Policy | Lists | Rationale |
|---|---|---|---|
| DEFAULT | `standard` | Multi PRO + TIF Mini | Unchanged (owner-approved A1/A2) |
| PC | `standard` | Multi PRO + TIF Mini | Unchanged |
| MOBILE | `standard` | Multi PRO + TIF Mini | Unchanged; social core protected |
| GAMING | `gaming` | Multi NORMAL + TIF Mini | Launchers and anti-cheat unaffected by all lists; Normal avoids Pro-only crash-reporting/telemetry blocks (e.g. `crash.steampowered.com`, `sentry.io`) |
| SMART-TV | `smart-tv` | Multi LIGHT + TIF Mini | Safest practical level: blocks Samsung/LG ad domains; avoids Normal/Pro-only blocks of Prime Video ad-roll hosts and Netflix logging |
| XBOX | `console` | Multi LIGHT + TIF Mini | Xbox essentials unaffected by any list; avoids Normal/Pro-only PlayFab title and Prime Video ad-roll blocks; Pro-only Microsoft telemetry not needed |

"Conservative" is not "no filtering": Light (≈34.5 k entries) plus TIF Mini (≈177.5 k malware/phishing entries) still blocks ads, trackers, telemetry and threats.

## 6. Italian filtering layer (design only)

| Category | Candidate source | DNS can do | DNS cannot do |
|---|---|---|---|
| Phishing / malware / scam | HaGeZi TIF Mini (already active); HaGeZi Fake (fake shops, subscription traps) | Block known malicious or fake **domains** | Detect a new phishing page on a legitimate or compromised site, or on a shared-hosting tenant not yet listed |
| Malvertising / pop-under networks | HaGeZi Pop-Up Ads | Block known pop-up / pop-under **ad-network domains** | Stop JavaScript pop-ups, new tabs or redirects executed by an otherwise legitimate domain's own scripts |
| Gambling | HaGeZi Gambling mini; ADM list of sites blocked in Italy (official, to be evaluated) | Block gambling domains per group | Distinguish licensed vs illegal operators on the same CDN |
| Adult | HaGeZi NSFW | Block adult domains per group | Filter content inside general platforms (social networks, search, video) |
| Italian-specific scams | Manual deny rules with metadata (`config/rules/deny.yaml`) from verified reports (e.g. CERT-AgID alerts) | Block specific reported domains, optionally with expiry | Anything path-based (`site.it/scam-page`) or IP-based |

- **Nothing enabled.** No candidate is enabled in A3. Each one requires an owner decision (adding a list), a measurement run and sanity limits, per ADR 0003/0004.
- **Encrypted DNS limits.** DNS filtering never sees URLs, page content or JavaScript, and apps using their own encrypted DNS can bypass it (D3).

## 7. Safety gates (unchanged, plus reinforcement)

- **A2 gates stay intact:** tripwire hard gate, `--accept-anomalies` scope, keep-previous behaviour.
- **A3 adds real protected data.** The tripwire now has 200+ domains to check. Activation stays development-only.
- **Validation:** config validation rejects deny rules and regexes touching protected domains, and regex rules outside the portable subset.
- **Tests guard against over-broad protection:** known telemetry names (e.g. `beacons.xboxlive.com`, `track.mp.microsoft.com`, `sonar-*.xx.fbcdn.net`) must stay blockable.

## 8. Test strategy

| Level | What |
|---|---|
| Unit: regex subset | Accepted constructs; rejected `\d \w \s \b`, lookaround, lazy quantifiers, backreferences, POSIX classes, backslash inside brackets, bad intervals, uppercase |
| Unit: policy engine | Precedence of all 7 layers, exact vs subtree, expiry, per-group lists, unknown group, match details |
| Config regression (offline) | Committed config + a **hostile** synthetic blocklist that blocks every catalogued endpoint and its parents: every protected/compatibility endpoint is allowed for every group; must-stay-blockable telemetry is still blocked; group-specific list mapping; security categories blocked everywhere |
| Compatibility catalog (`tests/data/compatibility.yaml`) | Per service: YouTube, Twitch, Netflix, Prime Video, Disney+, DAZN, Google, Microsoft, Apple, Amazon, Steam, Xbox, PlayStation, social networks, Italian services, banks, infrastructure |
| Tripwire | Real protected set vs synthetic lists (exact, covering parent, inside subtree, tenant of apex guard) |
| CLI | `policy explain` text/JSON, unknown group, artifacts from the local store |
| Network (manual, excluded from `make test`) | Real HaGeZi Light/Normal/Pro/TIF Mini: 0 tripwire hits; compatibility catalog allowed for each group's policy |
