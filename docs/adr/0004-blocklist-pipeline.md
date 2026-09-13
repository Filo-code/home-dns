# ADR 0004: Blocklist Pipeline

| Field | Value |
|---|---|
| **Status** | Accepted (sanity-limit values pending owner approval) |
| Date | 2026-09-13 |
| Decision owner | Project owner (13-step order, sources, freshness and anomaly policy approved 2026-09-13) |
| Related | [ADR 0003](0003-configuration-model.md) · [measurements](../research/2026-09-13-hagezi-measurements.md) · [blocklists.md](../blocklists.md) |

## Context

- **Lists are untrusted input.** Blocklists are downloaded from third-party mirrors. A bad list (truncated, stale, HTML error page, wrong file, or one that blocks a bank or `googlevideo.com`) could break the home network.
- **Downloading is not validation.** The owner requires that HTTP 200 is never treated as validation.
- **Recoverability.** Every deployment must be recoverable.
- **Replaceability.** The design must keep the filter engine replaceable (later technology review) and work offline in tests.

## Decision

### Modules

| Module | Role |
|---|---|
| `core.blocklists` (pure) | header parsing, adblock/hosts/domains parsing, normalization, deduplication, tripwire, artifact rendering and re-parsing, delta, sanity verdict |
| `pipeline.fetch` | HTTP transport only: streaming, byte cap, no redirects, errors as `FetchError` |
| `pipeline.blocklists` | the 13 steps, source selection, outcomes, alerts |
| `storage.artifacts` | content-addressed artifact store with `current`/`previous`, atomic writes, integrity check, rollback |
| `DnsProvider.deploy_blocklist` / `lookup_domain` | provider-neutral test deployment and health lookups; contract-tested |
| CLI `home-dns blocklists update\|status\|rollback` | dry-run by default, `--apply`, `--accept-anomalies`; development-only until C3 |

`pipeline` never imports `config` or concrete providers. This is enforced by the architecture test.

### Steps and source selection

1. **Steps 1–7 run per download attempt,** primary (jsDelivr) first, then fallback (GitHub raw): download → HTTP/content (200, `text/plain`, not HTML, UTF-8) → size guard → format and header date → parse → normalization (invalid-ratio guard) → deduplication (declared count must equal parsed rules).
2. **An attempt is accepted only if every step passes and** `Last modified` is within `max_age_hours` (48 h) and not in the future.
3. **If no attempt is accepted** (both failed, stale or suspicious), the **previous active artifact is kept** and a warning alert is raised. A questionable list is never deployed.
4. **Steps 8–13 run on the accepted attempt:** protected-domain tripwire → syntax validation (the rendered artifact must re-parse to the identical entry set) → sanity → test deployment → health check → activation.

### Gates and outcomes

| Condition | Outcome | Previous artifact | Alert |
|---|---|---|---|
| All steps pass, `--apply` | `activated` | becomes `previous` | info `blocklist_updated` |
| All steps pass, dry-run | `would_activate` | unchanged | — |
| Same content as active | `unchanged` | unchanged | — |
| No acceptable download | `kept_previous` | kept | warning `blocklist_update_failure` / `suspicious_blocklist` |
| Protected domain hit | `blocked_by_tripwire` (fallback **not** tried; `--accept-anomalies` cannot bypass) | kept | **critical** `protected_domain_tripwire_failure` |
| No protected domains configured | dry-run: warning; `--apply`: `blocked_by_tripwire` | kept | warning / critical |
| Sanity limit exceeded | `held_for_review` (unless `--accept-anomalies` after manual review) | kept | warning `suspicious_blocklist` |
| Hard sanity failure (0 valid entries) | `failed` | kept | warning |
| Artifact re-validation, test deployment, health check or activation fails | `failed` | kept | critical `failed_deployment` / `health_check_failure` |

### Other decisions

- **Deterministic artifacts.** Artifacts carry no timestamps: identical content gives an identical SHA-256, so an `unchanged` result is detectable. Timestamps and statistics are stored in a separate metadata JSON.
- **Isolated test deployment.** Test deployment goes to a **fresh, isolated test provider** (`MockDnsProvider`) for every source. Production activation to Pi-hole is a separate step, added in C3; A2 activation only updates the local artifact store.
- **Limits require evidence and approval.** Sanity limits are optional per source (`sanity:` in `sources.yaml`) and applied only after owner approval of measured values. Without them, the size and delta checks are skipped and reported.
- **Offline testing.** Tests never use the network. One `network`-marked test runs the real lists from both mirrors through the pipeline in dry-run.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Treat HTTP 200 as success | Explicitly rejected by the owner; captive portals, truncation and stale mirrors all return 200 |
| Use a stale primary if the fallback fails | Would deploy a questionable list; the owner requires keeping the previous valid list |
| Fixed ±20 % change limit as a hard failure | Unsupported by evidence; a legitimate TIF release changed +5.85 % in one version; large changes are anomalies for review |
| Try the fallback on a tripwire hit | The hit is a content/policy problem, not a transport problem; both mirrors serve the same content |
| Let Pi-hole download lists directly (adlist URLs) | Bypasses validation and the tripwire; Pi-hole will instead be fed validated local artifacts (C2/C3) |

## Consequences

- **Activation is refused until A3 seeds protected domains.** The tripwire cannot verify anything while the protected set is empty. This is intended.
- **Old artifacts accumulate (~4–5 MB each).** Retention and cleanup belong to A4, before any unattended scheduling.
- **Sanity limits remain unconfigured** until the owner approves the proposal in the measurement report.
- **A real provider** (`PiHoleV6Provider`, C2) must pass the same `deploy_blocklist`/`lookup_domain` contract tests as the mock.
