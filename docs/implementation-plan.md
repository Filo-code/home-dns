# Implementation Plan (revised 2026-09-13)

> **Status: approved by owner 2026-09-13** (with decisions recorded in §9).
> At the owner's request, this replaces the linear phase order in `CLAUDE.md` §48. The software is built and tested offline first. Integration with the Raspberry Pi and the Fastweb network comes last.

## 1. Principles

1. **Offline first.**
   - Stage A runs entirely on the development machine.
   - No changes to the Raspberry Pi or the network.
   - No Pi-hole or Unbound installed anywhere.
2. **Provider abstraction.**
   - All code talks to a `DnsProvider` interface.
   - Stage A ships only a `MockDnsProvider`.
   - `PiholeV6Provider` is added in Stage C and must pass the same contract tests.
3. **No hard-coded environment.**
   - Addresses, interfaces, paths, thresholds, cooldowns and device inventories are **placeholders**, validated at load time.
   - A config with unresolved placeholders **refuses to run in production mode**.
4. **Everything testable before deployment.**
   - Every component ships with automated tests in the same phase. Tests are not left for the end.
   - Time, filesystem, disk usage, network and Telegram are injected, so tests are deterministic.
5. **Safe by default.**
   - Dry-run and mock modes are the default.
   - Real side effects (Telegram send, provider writes, file deletion) require explicit configuration.
6. **Small, reviewed increments.**
   - Each phase ends with passing tests, updated docs, an ADR where a real decision was made, and a commit.

## 2. Stage overview

| Stage | Where | Touches Pi / network? | Phases |
|---|---|---|---|
| **A — Offline software** | Development machine | **No** | A0–A9 |
| **B — Pre-deployment audits** | Pi + Box Seven | Read-only | B1–B3 |
| **C — Pi deployment, isolated** | Pi only; no client uses it yet | Pi yes, network no | C1–C5 |
| **D — Network integration** | LAN / router | Yes, each change approved | D1–D5 |

ADR 0001 gates G1–G5 still block Stage C. Gate G6 still blocks device-policy rollout (D2).

## 3. Stage A — Offline software

### A0 — Foundations ✅ (done 2026-09-13, see [specs/a0-foundations.md](specs/a0-foundations.md))
- **Goal:** agree the software stack; create an empty, testable skeleton.
- **Deliverables:**
  - ADR 0002 (software stack and tooling)
  - project layout, dependency pinning, formatter and linter, `make test`
  - config loader skeleton with placeholder detection
  - local check script that mirrors CI
- **Exit:** `make test` passes on the skeleton; placeholder detection has tests.

### A1 — Configuration architecture ✅ (done 2026-09-13, see [ADR 0003](adr/0003-configuration-model.md))
- **Goal:** one validated, provider-neutral model of what the system should do.
- **Deliverables:** schemas, loader and a `validate-config` CLI covering:
  - device groups (DEFAULT, PC, GAMING, MOBILE, SMART-TV, XBOX)
  - policy model: group → categories → lists + exceptions
  - protected domains, by category, each with a reason and a source
  - allowlist / denylist / regex rule files, each rule with reason, owner, date and groups
  - blocklist source catalog: URL, format, category, license, update interval
  - environment / placeholder templates
  - ADR 0003 (configuration model)
- **Tests:**
  - schema validation, including rejection of bad files
  - duplicate and conflicting rules
  - references to unknown groups
  - unresolved placeholders in production mode
- **Depends on:** A0

### A2 — Blocklist pipeline ✅ (done 2026-09-13, see [ADR 0004](adr/0004-blocklist-pipeline.md); parameters approved 2026-09-13)
- **Goal:** turn untrusted list sources into validated, versioned, deployable artifacts that can be rolled back.
- **Stages (owner-approved order, 2026-09-13):**
  1. download success
  2. HTTP/content correctness
  3. reasonable file size
  4. expected content format
  5. parsing
  6. normalization
  7. deduplication
  8. protected-domain tripwire
  9. syntax/rule validation
  10. sanity checks
  11. test deployment (mock provider)
  12. health check
  13. activation

  Any suspicious or invalid result aborts before deployment and keeps the previous artifact. HTTP 200 alone is never sufficient. Sources: jsDelivr primary, `raw.githubusercontent.com` fallback.
- **Deliverables:**
  - pipeline CLI, `--dry-run` by default
  - content-addressed artifact store (current / previous / backup-2; older versions pruned atomically)
  - atomic activation and rollback
  - pipeline report (JSON)
  - sanity checks:
    - minimum and maximum entry count
    - maximum change versus the previous version
    - IP, wildcard, TLD-only, localhost and private entries
    - IDN/punycode
    - encoding problems and oversize input
  - ADR 0004 (blocklist strategy)
- **Tests** (fixture lists; no real downloads needed):
  - a protected domain in a list → **abort and keep the previous list**
  - corrupt, empty, truncated, or HTML-instead-of-list downloads
  - huge size deltas
  - mixed hosts / adblock / plain formats
  - deduplication across lists
  - rollback restores the exact previous artifact
- **Depends on:** A1

### A3 — Filtering logic ✅ (done 2026-09-14, see [ADR 0009](adr/0009-filtering-policy.md))
- **Goal:** decide *what* each group blocks, and prove it with tests.
- **Deliverables:**
  - **List catalog research** per category — ads/trackers, malware/phishing, telemetry, gambling, adult, Italian ads/trackers:
    - source
    - license
    - maintenance activity
    - false-positive history
  - **Regex architecture:**
    - rules restricted to a documented, portable POSIX ERE subset
    - a validator that rejects anything outside that subset
    - the Python and POSIX regex engines differ, so behaviour is re-verified on real Pi-hole in C2
  - **Custom Italian rules.**
  - **Compatibility exceptions,** each with a reason and a test:
    - YouTube / `googlevideo.com`
    - Twitch
    - Xbox / Microsoft
    - Smart TV streaming, DRM and casting
    - social networks
    - Apple, Google and Amazon services
  - **Protected-domain database**, seeded from verified sources:
    - Italian public services
    - banks and payment services
    - technology companies
    - internet infrastructure
  - **Policy resolver:** answers "for group G, is domain D blocked, allowed or protected, and why?"
- **Tests:**
  - table-driven policy tests per group, e.g. "SMART-TV + netflix.com → allowed", "DEFAULT + known ad domain → blocked"
  - regex validator tests
  - exception precedence tests
- **Depends on:** A1, A2

### A4 — Storage and maintenance
- **Goal:** never fill the disk, never lose configuration, keep SD-card writes as low as practical.
- **Deliverables:**
  - **`storage_guard`:** under 70% healthy · 70–80% warning · 80–90% automatic cleanup · over 90% emergency cleanup + critical alert
  - **`cleanup`** with retention policies: query history (~30-day target), logs, artifacts, backups
  - **`health_check`** framework with pluggable checks (shared with A5)
  - **`backup`:**
    - covers config, policies, device mappings, dashboard config and pipeline state
    - provider export goes through the interface, and Unbound config is included (ADR 0001 T2)
    - checksums and a manifest
  - **`restore`** with verification and dry-run. **Restore is tested, not assumed.**
  - **SD-card-safe write strategy:**
    - batched writes and atomic rename
    - append-only files where possible
    - tmpfs for transient state
    - configurable data dir, for the SSD migration
  - ADR 0007 (storage strategy)
- **Tests:**
  - fake disk-usage provider covering every threshold band
  - cleanup never deletes outside allowed paths
  - backup → restore round trip is byte-identical
  - corrupted backups are detected
- **Depends on:** A1

### A5 — Monitoring
- **Goal:** turn raw checks into incidents without flapping or spam.
- **Deliverables:**
  - health model: check result → component status
  - incident state machine: `OK → SUSPECT → INCIDENT → RECOVERING → OK`
  - thresholds in config (placeholders until the Pi baseline, gate G2)
  - retry and backoff, with a restart budget (no infinite restart loops)
  - cooldown and deduplication keys
  - recovery detection
  - **blocklist freshness escalation** (owner decision 2026-09-13), per source:
    - 1st consecutive run that kept the previous artifact because both mirrors were stale or failed → warning
    - 2nd consecutive such run → warning
    - 3rd consecutive such run → **critical** Telegram alert
    - any successful valid update (`activated` or `unchanged`) resets the counter
    - escalation only notifies: it never changes filtering policy, never bypasses a safety gate and never deploys a questionable list
- **Tests:**
  - simulated clock
  - blocklist escalation: warning, warning, critical on three consecutive stale/failed runs; reset after a valid update
  - flapping inputs
  - a long outage produces exactly one alert, then one recovery
  - an exhausted restart budget escalates and stops restarting
- **Depends on:** A4 (health_check framework)

### A6 — Telegram alerting
- **Goal:** reliable, non-spammy, secret-safe notifications.
- **Deliverables:**
  - `Notifier` interface with three implementations:
    - `MockNotifier` (in-memory)
    - `FileNotifier` (local outbox for manual review)
    - `TelegramNotifier`
  - severity routing: CRITICAL / WARNING / INFO
  - message formatting, in Italian or English (owner to choose)
  - anti-spam wired to the A5 incident engine
  - secrets:
    - read only from the environment or a systemd `EnvironmentFile`
    - refuse to start if the secret file is readable by group or others
    - token redacted in logs
  - Telegram outage handling: bounded queue and retry; a Telegram failure never crashes the monitored system
  - ADR 0006 (Telegram alerting)
- **Tests:**
  - routing
  - cooldown and deduplication
  - recovery messages
  - redaction
  - permission checks
  - HTTP errors and rate limiting, against a mocked Telegram API
- **Optional, owner-approved:** one manual live send to the owner's bot. It needs Internet access only, no network changes.
- **Depends on:** A5

### A7 — Backend
- **Goal:** the dashboard's server, fully usable with mock data.
- **Deliverables:**
  - **ADR 0005** (backend and dashboard architecture).
  - **`DnsProvider` abstraction:**
    - operations: stats, query log, clients, groups, lists, domains/rules, system metrics, backup export
    - `MockDnsProvider` with realistic generated data: 16 sample devices, IPv4 plus rotating IPv6, a blocked/allowed mix
    - fixtures shaped after the official Pi-hole v6 API spec
  - **Device model:** identity (MAC / IPv4 / IPv6 correlation), custom names, groups, first and last seen.
  - **Metrics model:** QPS, block %, cache hit ratio, latency p50/p95, per-device counters.
  - **Historical data model:** SQLite rollups (minute → hour → day), retention, batched writes.
  - **Security model:**
    - LAN-only bind (address is a placeholder)
    - authentication, session and CSRF protection, rate limiting
    - least-privilege provider credentials
    - no secrets in API responses
  - **REST API** for the dashboard, including alert and configuration views.
- **Tests:**
  - provider contract test suite (the mock must pass it now; the real provider must pass it in C2)
  - API tests
  - auth and permission tests
  - rollup correctness and retention
- **Depends on:** A1. Can run in parallel with A4–A6.

### A8 — Dashboard
- **Goal:** a responsive UI that works entirely on mock data.
- **Deliverables:**
  - pages: Overview, Devices, Security, Performance, Alerts, Configuration
  - layouts for desktop, iPad and mobile
  - charts
  - mock/demo mode
  - basic accessibility
- **Tests:**
  - component tests
  - end-to-end browser tests at three viewport sizes against the mock backend
- **Depends on:** A7

### A9 — Offline integration rehearsal
- **Goal:** prove the whole system works together before touching hardware.
- **Deliverables:**
  - end-to-end rehearsal in mock mode: pipeline → mock provider → backend → dashboard → incidents → mock Telegram
  - full test run, coverage review, security review, documentation pass
  - "ready for Stage B" checklist
- **Exit:** all suites green; the only unresolved placeholders are those marked `audit-required`.

## 4. Stage B — Pre-deployment audits (read-only)

| Phase | Content | Gate |
|---|---|---|
| B1 | Raspberry Pi audit + resource baseline | G1, G2 |
| B2 | Fastweb Box Seven network audit: DNS interception, IPv4/IPv6 DNS behaviour | G3, G4, G5 |
| B3 | Re-check ADR 0001 against B1/B2 findings (triggers R1–R7); resolve `audit-required` placeholders; update ADRs | — |

## 5. Stage C — Pi deployment, isolated

During Stage C, no client or router points at the Pi.

| Phase | Content |
|---|---|
| C1 | Install Pi-hole + Unbound (**explicit approval required**). Base DNS. DNS/DNSSEC tests by querying the Pi directly |
| C2 | Implement `PiholeV6Provider`; run the contract tests against the real instance; re-verify regex behaviour |
| C3 | Pipeline in staging, then the core lists. Storage guard, monitoring and Telegram go live. **Before this step:** re-measure the HaGeZi lists over ≥ 30 days and propose sanity-limit refinements (owner decision 2026-09-13). The blocklist update timer runs every `update_interval_hours` (24 h), read from config |
| C4 | Backend + dashboard on the Pi (LAN-only) |
| C5 | Real backup → restore test on the Pi. Rehearse rollback of a Pi-hole update (ADR 0001 T3) |

## 6. Stage D — Network integration (each change approved, with an undo plan)

| Phase | Content |
|---|---|
| D1 | Pilot: 1–2 devices pointed at the Pi manually |
| D2 | Device policies on the real network; gate G6 (IPv6/MAC group behaviour) |
| D3 | IPv6 DNS strategy and DNS-bypass mitigation (ADR 0008) |
| D4 | Network-wide cutover via router/DHCP, with a rollback plan |
| D5 | Soak period; performance measured against the baseline; final documentation |

## 7. Where the original CLAUDE.md §48 phases went

| Original phase | New location |
|---|---|
| 1 Raspberry Pi audit | B1 |
| 2 Network audit | B2 (interim snapshot already done) |
| 3–4 Architecture comparison / approval | Done (ADR 0001); re-checked in B3 |
| 5–7 DNS install / base DNS / DNS testing | C1 |
| 8 Core filtering | A2 + A3 (offline), C3 (live) |
| 9 Italian filtering | A3 (offline), C3 (live) |
| 10 Device policies | A1 + A3 (model), D2 (live) |
| 11 IPv6 + DNS bypass | D3 |
| 12 Maintenance | A4 + A5 (offline), C3 (live) |
| 13 Telegram | A6 (offline), C3 (live) |
| 14 Dashboard | A7 + A8 (offline), C4 (live) |
| 15 Testing | Every phase, plus A9 and C2/C5 |
| 16 Backup/restore | A4 (offline), C5 (live) |
| 17 Documentation | Every phase, plus A9 and D5 |

## 8. Parallelization (CLAUDE.md §12)

- **Sequential:** A0 → A1. After A1, **A2 and A3 may run in parallel** (owner decision 2026-09-13); A3 uses fixtures and local data. Both depend on the A1 config model, so schema changes go through the lead.
- **Two tracks after A1**, in separate worktrees:
  - Track 1: A4 → A5 → A6
  - Track 2: A7 → A8
- **Research in parallel:** list catalog and protected-domain sources, as read-only agent work.
- **Merging:** the lead reviews, tests and merges each track. No two agents edit the same config schema at the same time.

## 9. Owner decisions (2026-09-13)

1. **Stack (ADR 0002):** Python 3.11+, FastAPI, Pydantic / pydantic-settings, SQLite behind a small repository/storage layer, pytest, httpx. Frontend: TypeScript + React + Vite, built on the Mac; only static files reach the Pi; no Node.js on the Pi in production.
2. **Blocklists:** real downloads, real processing and real tests of **HaGeZi Multi PRO** and **HaGeZi TIF Mini** are allowed on the Mac. **No real deployment.** No other lists without a documented reason and an explicit decision.
3. **Local Pi-hole:** a temporary Pi-hole v6 container on the Mac is allowed **only** for adapter contract/integration tests. It must stay separate from production and never become a parallel production. `DnsProvider` → `MockDnsProvider` | `PiHoleV6Provider`; the **same** contract tests run against both. The mock must work without hardware or the home network.
4. **Languages:** Telegram messages and dashboard UI in **Italian**; code, variables, technical logs and technical documentation in **English**.
5. **Dependencies:** after A1, A2 and A3 may proceed in parallel (A3 can use fixtures and local data without waiting for A2 to finish).
