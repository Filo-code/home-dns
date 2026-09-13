# ADR 0003: Filtering Configuration Model

| Field | Value |
|---|---|
| **Status** | Accepted |
| Date | 2026-09-13 |
| Decision owner | Project owner (groups, rule metadata and download sources approved 2026-09-13) |
| Related | [ADR 0001](0001-dns-architecture.md) · [ADR 0002](0002-software-stack.md) · [implementation-plan.md](../implementation-plan.md) |

## Context

The system needs one provider-neutral description of *what* to filter for whom, covering:
- device groups;
- policies;
- manual allow/deny/regex rules;
- protected domains;
- the approved blocklist sources.

It must satisfy these requirements:
- **Validation before use.** It is validated before anything else (pipeline A2, resolver A3, backend A7) consumes it.
- **Provider-independent.** It works unchanged when Pi-hole v6 is integrated (C2), and survives a later filter-engine / resolver technology review.
- **No real network identifiers** in the repository.
- **Extensible:** new groups, lists or rules are added through configuration only.

## Decision

### Layers (fits the A0 boundaries)

| Layer | Module | Content |
|---|---|---|
| Domain model (pure) | `home_dns.core.filtering`, `home_dns.core.domains` | Pydantic models, domain normalization, cross-reference checks. No YAML, no I/O |
| File schemas + loading | `home_dns.config.filtering` | One schema per file, `schema_version: 1`, hygiene checks reused from A0 |
| Reporting | `home-dns validate-config` | Filtering summary + issues; exit 2 on schema or cross-reference errors |

### Files

| File | Holds |
|---|---|
| `config/groups/groups.yaml` | `groups: [{id, description, policy}]` |
| `config/policies/policies.yaml` | `policies: [{id, description, blocklists: [source ids]}]` |
| `config/blocklists/sources.yaml` | `sources: [{id, name, homepage, license, format, categories, urls{primary, fallback}, update_interval_hours}]` |
| `config/rules/allow.yaml`, `deny.yaml` | `rules: [{domain, include_subdomains, reason, author, created_at, groups, source, expires_at?}]` |
| `config/rules/regex.yaml` | `rules: [{pattern, action: allow\|deny, reason, author, created_at, groups, source, expires_at?}]` |
| `config/protected-domains/<category>.yaml` | `{category (= file name), description, domains: [{domain, include_subdomains, reason, source}]}` |

### Rules of the model

1. **Groups.**
   - The six approved groups: DEFAULT, PC, GAMING, MOBILE, SMART-TV, XBOX.
   - Ids are upper-case words joined by `-`. `DEFAULT` is mandatory.
   - Adding a group is a configuration change only; a test proves this with an `IOT` group.
2. **Device assignments are not configuration files.**
   - Device → group mappings, names and identifiers belong to backend storage (A7), editable from the dashboard.
   - This keeps real MAC/IP/hostnames out of Git.
3. **Group → exactly one policy.**
   - A policy lists blocklist source ids explicitly.
   - Source `categories` (advertising, tracking, telemetry, malware, phishing, gambling, adult) are descriptive. They feed security statistics, not selection.
   - Explicit ids make "which list affects which group" reviewable.
   - Current policy contents are **provisional** until A3.
4. **Rule metadata:**

   | Field | Required | Meaning |
   |---|---|---|
   | `reason` | yes | why the rule exists |
   | `author` | yes | who added it |
   | `created_at` | yes | date the rule was added |
   | `groups` | yes | target group ids, or `["*"]` for all groups |
   | `source` | yes | where the rule came from |
   | `expires_at` | no | timezone-aware datetime, after `created_at` |

   - Expired rules are ignored automatically and reported as `info`, so temporary compatibility exceptions cannot become permanent.
   - No approval workflow, tags or history: deliberately minimal.
5. **Domains.**
   - Domains are normalized: lower case, trailing dot removed, IDNA/punycode.
   - Rejected values: wildcards (use `include_subdomains`), IP literals, single-label names, invalid labels.
   - The same normalization will be used by the A2 pipeline.
6. **Regex rules.**
   - A1 checks syntax, maximum length (512), and rejects patterns that match the empty string.
   - The portable POSIX-ERE subset required by Pi-hole is A3.
7. **Cross-reference errors:**
   - missing DEFAULT;
   - unknown policy, source or group references;
   - duplicate ids;
   - duplicate or conflicting (allow vs deny) **active** rules for overlapping groups;
   - an active deny rule or deny regex that would block a protected domain (in either direction of the subdomain relation);
   - duplicate protected entries.

   **Warnings:** an empty protected-domain set.

   **Info:** unused policies or sources, expired rules.
8. **Blocklist sources.**
   - HTTPS only, with a `primary` and an optional distinct `fallback` URL.
   - Approved: HaGeZi Multi PRO and HaGeZi TIF Mini, jsDelivr primary, `raw.githubusercontent.com` fallback.
   - No other list without a documented reason and an explicit owner decision.
9. **HTTP 200 is not validation.**
   - The A2 pipeline must pass, in order: download success → HTTP/content correctness → reasonable size → expected format → parsing → normalization → deduplication → protected-domain tripwire → syntax/rule validation → sanity checks → test deployment → health check → activation.
   - Anything suspicious aborts before deployment.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Groups select lists by category | Multi-category lists (e.g. HaGeZi Multi PRO) make category selection ambiguous; explicit ids are auditable |
| Devices listed in `groups.yaml` | Real identifiers would enter Git; the dashboard must be able to change assignments |
| One big YAML file | Harder to review; per-concern files map to ownership and error messages name the exact file |
| Rule history/approval workflow | Over-engineering for a single-owner home system; Git history already records changes |
| Date-only `expires_at` | Ambiguous timezone and time of day; a timezone-aware datetime is explicit |

## Consequences

- **Consumers use validated models only.** A2, A3 and A7 consume `FilteringConfig` models, never raw YAML.
- **The protected-domain set is empty until A3,** so `validate-config --strict` fails on the warning. This is intentional: the tripwire must not be considered active yet.
- **Adapters own translation.** Provider-specific mapping (Pi-hole groups, adlists, domain entries) belongs to the provider adapter (C2), not to this model. That keeps a future filter-engine change contained.
