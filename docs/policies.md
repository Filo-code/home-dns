# Policies

> **Status:** implemented and tested offline (A3). **Nothing is deployed.** Design: [specs/a3-filtering-policy.md](specs/a3-filtering-policy.md) · Decision: [ADR 0009](adr/0009-filtering-policy.md) · Evidence: [evaluation](research/2026-09-14-a3-policy-evaluation.md).

## Groups and policies

| Group | Policy | Lists | Intent |
|---|---|---|---|
| DEFAULT | `standard` | HaGeZi Multi PRO + TIF Mini | Unassigned devices |
| PC | `standard` | Multi PRO + TIF Mini | Windows PCs |
| MOBILE | `standard` | Multi PRO + TIF Mini | Phones and iPads; social networks fully functional |
| GAMING | `gaming` | Multi NORMAL + TIF Mini | Gaming PCs; launchers, anti-cheat, voice unaffected |
| SMART-TV | `smart-tv` | Multi LIGHT + TIF Mini | Streaming, DRM, casting, stores and updates preserved |
| XBOX | `console` | Multi LIGHT + TIF Mini | Xbox network, Store, Game Pass, multiplayer, party preserved |

- **Assignments:** devices are assigned to groups in backend storage (A7), not in Git.
- **Unassigned devices** use DEFAULT.

## How a decision is made

For one group and one domain, the first match wins:

1. **Protected domain** → allowed
2. **Allow rule** (`config/rules/allow.yaml`) → allowed
3. **Allow regex** (`config/rules/regex.yaml`, `action: allow`) → allowed
4. **Deny rule** (`config/rules/deny.yaml`) → blocked
5. **Deny regex** → blocked
6. **A list used by the group's policy** → blocked
7. **Otherwise** → allowed

Expired rules (`expires_at` in the past) are ignored.

```bash
# Why is this domain blocked/allowed for a Smart TV?
PYTHONPATH=src uv run --locked python -m home_dns.cli policy explain --group SMART-TV www.netflix.com ads.example.com
```

The command uses the active local artifacts (`home-dns blocklists update --apply` in development). Lists without an active artifact are reported as "not evaluated".

## Common changes (configuration only)

| Goal | Change |
|---|---|
| Temporarily allow a domain for Smart TVs | Add to `config/rules/allow.yaml` with `groups: [SMART-TV]` and `expires_at` (timezone required). Run `validate-config` |
| Block a domain for everyone | Add to `config/rules/deny.yaml` with `groups: ["*"]`. Refused if it touches a protected domain |
| Give XBOX its own list set | Edit the `console` policy in `config/policies/policies.yaml` |
| Protect a critical domain | See [protected-domains.md](protected-domains.md) |

Regex rules must use the portable subset:
- **allowed:** literals, `.`, `^`, `$`, `|`, groups, brackets with ranges, `* + ? {m,n}`;
- **rejected:** `\d \w \s \b`, lookarounds, lazy quantifiers, backreferences, POSIX classes, upper-case letters.

## What DNS filtering can and cannot do

| DNS filtering **can** | DNS filtering **cannot** |
|---|---|
| Block known ad, tracker, telemetry, malware, phishing, scam, gambling and adult **domains** | See URLs, paths or page content (`legit-site.it/scam-page`) |
| Block known pop-up / pop-under ad-network domains | Stop JavaScript pop-ups, new tabs or redirects run by a legitimate site's own scripts |
| Apply different lists per device group | Filter content inside general platforms (social networks, search, video) |
| Protect critical domains from accidental blocking | Detect a brand-new phishing page on a compromised or shared-hosting domain before it is listed |
| Answer every client that uses the Pi as its resolver | Filter devices that use their own encrypted DNS (DoH/DoT/DoQ) or a VPN (D3 addresses detection/mitigation) |

## Italian filtering layer (design; nothing enabled)

| Category | Candidate | Status |
|---|---|---|
| Phishing / malware / scam | HaGeZi TIF Mini (active); HaGeZi Fake | Fake: needs owner decision + measurement |
| Malvertising / pop-under networks | HaGeZi Pop-Up Ads | Needs owner decision + measurement |
| Gambling | HaGeZi Gambling mini; ADM list of sites blocked in Italy | Needs owner decision; ADM format and licensing to be evaluated |
| Adult | HaGeZi NSFW | Needs owner decision; per-group only |
| Italian-specific scams | Manual deny rules from verified reports (e.g. CERT-AgID), with `expires_at` where appropriate | Mechanism ready; no entries without verified evidence |

## Hard rules from CLAUDE.md, whatever the policy

- **YouTube:** never block `googlevideo.com` or YouTube/Google video infrastructure (§25). Protected as a subtree.
- **Twitch:** never block streaming, chat, authentication or CDN (§26). `ttvnw.net`, `jtvnw.net`, `twitchcdn.net` and the chat/auth hosts are protected.
- **Social networks:** keep them fully functional. Core domains and media hosts are protected; only ad/telemetry subdomains stay blockable (§24).
