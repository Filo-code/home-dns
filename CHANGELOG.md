# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Dates are ISO 8601.

## [Unreleased]

### Added
- 2026-09-13 — Documentation-based comparison of Pi-hole + Unbound, AdGuard Home and Technitium DNS Server (`docs/architecture-comparison.md`).
- 2026-09-13 — ADR 0001: Pi-hole v6 + Unbound, *approved for implementation planning — pending Raspberry Pi audit and final Fastweb Seven network validation* (`docs/adr/0001-dns-architecture.md`).
- 2026-09-13 — Initial project scaffold: documentation placeholders, configuration templates (no deployable values), directory structure, `.gitignore`, `.env.example`.
- 2026-09-13 — Interim network snapshot (`docs/audits/2026-09-13-interim-network-snapshot.md`).

### Added — A0 foundations
- 2026-09-13 — ADR 0002 (software stack) and A0 technical specification (`docs/specs/a0-foundations.md`).
- 2026-09-13 — Python package `home_dns` with:
  - pure core models
  - config loading with `HOME_DNS_*` overrides
  - placeholder model (`<<REQUIRED:…>>` / `<<AUDIT:…>>`) and readiness evaluation (development vs production)
  - `DnsProvider` interface + deterministic `MockDnsProvider`
  - SQLite storage boundary with dry-run-by-default migrations
  - FastAPI `/api/v1/health`
  - composition root
  - `home-dns validate-config` / `serve` CLI
- 2026-09-13 — Application profiles `config/app/development.yaml` and `config/app/production.example.yaml`.
- 2026-09-13 — Test suite:
  - unit, contract (provider-agnostic), API and architecture tests (import boundaries; no real network values)
  - offline network guard
  - 90 % coverage gate
- 2026-09-13 — Frontend skeleton (React + Vite + TypeScript, Italian UI) with a Vitest test; `Makefile` with setup/test/lint/check.

### Added — A1 configuration architecture
- 2026-09-13 — ADR 0003 (filtering configuration model) and technical-debt register (`docs/technical-debt.md`).
- 2026-09-13 — `home_dns.core.domains`: domain normalization (IDNA, no wildcards/IPs/single labels) and subdomain matching.
- 2026-09-13 — `home_dns.core.filtering`: groups, policies, blocklist sources (HTTPS primary/fallback), allow/deny/regex rules with `reason`, `author`, `created_at`, `groups`, `source`, optional `expires_at`, and protected domains. Cross-reference checks cover unknown refs, duplicates, allow/deny conflicts, deny-vs-protected and expiry.
- 2026-09-13 — `home_dns.config.filtering` loader with one schema per file; `validate-config` reports the filtering summary and issues.
- 2026-09-13 — Configuration files:
  - `config/groups/groups.yaml` (6 groups)
  - `config/policies/policies.yaml` (provisional)
  - `config/blocklists/sources.yaml` (HaGeZi Multi PRO + TIF Mini)
  - `config/rules/{allow,deny,regex}.yaml`
  - `config/protected-domains/{italian,technology,infrastructure}.yaml` (empty until A3)

### Added — A2 blocklist pipeline
- 2026-09-13 — ADR 0004, operational guide `docs/blocklists.md`, measurement report `docs/research/2026-09-13-hagezi-measurements.md` with a sanity-limit proposal (not configured).
- 2026-09-13 — `core.blocklists`: header, adblock/hosts/domains parsing, normalization, deduplication, protected-domain tripwire, deterministic artifacts, delta and sanity verdicts.
- 2026-09-13 — `storage.artifacts`: content-addressed store, `current`/`previous`, atomic writes, integrity checks, dry-run rollback.
- 2026-09-13 — `pipeline.fetch` (httpx, byte cap, no redirects) and `pipeline.blocklists`:
  - the 13 steps in owner-approved order
  - jsDelivr → GitHub fallback with a 48 h freshness limit
  - keep the previous artifact when nothing is acceptable
  - anomalies held for review; tripwire as a hard gate
- 2026-09-13 — `DnsProvider.deploy_blocklist` (dry-run) and `lookup_domain`, with contract tests.
- 2026-09-13 — CLI `home-dns blocklists update|status|rollback`; `scripts/blocklists/measure_sources.py`; `network`-marked real-list test.
- 2026-09-13 — Source schema: `max_age_hours` (48 for both HaGeZi lists) and optional `sanity` limits.

### Added — A4 storage and maintenance
- 2026-09-14 — Design `docs/specs/a4-storage-maintenance.md`, ADR 0007, docs `storage.md` /
  `maintenance.md` / `backups.md` / `restore.md`.
- 2026-09-14 — `core.storage`: disk-usage thresholds (owner-approved 70/80/90 bands), pure
  `classify_usage`, retention policy, cleanup planning, `StorageReport` (the interface A5
  monitoring is expected to consume).
- 2026-09-14 — `paths.tmp_dir` added alongside the existing `data_dir`/`log_dir`/`backup_dir`.
- 2026-09-14 — `storage.artifacts.ArtifactStore.reconcile()`: prunes orphaned blocklist-artifact
  files without activating anything (purely additive; A2 retention unchanged).
- 2026-09-14 — `storage.sqlite` extended: online-backup-API database snapshots, `quick_check`/
  `integrity_check`, `wal_checkpoint`, and `VACUUM` (implemented, never called automatically —
  enforced by a regression test).
- 2026-09-14 — New modules `storage.disk`, `storage.tempfiles` (safe, non-recursive, symlink- and
  traversal-refusing sweep), `storage.logs` (size x count bounded rotation), `storage.backup`
  (checksummed, atomically-published, versioned backups with the newest-valid-never-pruned
  guarantee), `storage.report`, `storage.cleanup`.
- 2026-09-14 — `config/storage.py` loader for `config/storage/storage.yaml` (schema-owned,
  same pattern as `config/filtering.py`).
- 2026-09-14 — CLI: `home-dns storage status|cleanup|verify|backup|restore`, dry-run by default.
- 2026-09-14 — Tests: 119 new (831 total), coverage 97.39%.

### Added — A3 filtering policy
- 2026-09-14 — Design `docs/specs/a3-filtering-policy.md`, ADR 0009, evaluation report `docs/research/2026-09-14-a3-policy-evaluation.md`.
- 2026-09-14 — `core.policy.PolicyEngine`: pure decision for group + domain, with Pi-hole-compatible precedence and explanations.
- 2026-09-14 — `core.regex`: portable POSIX-ERE subset validator, enforced for regex rules.
- 2026-09-14 — 293 verified protected domains across italian, banking, technology, gaming, streaming, social and infrastructure. Each has a reason and an evidence source; subtree / exact / apex-guard tiers.
- 2026-09-14 — Policies `standard` (Pro + TIF Mini), `gaming` (Normal + TIF Mini), `smart-tv` and `console` (Light + TIF Mini). HaGeZi Light and Normal added to the catalog.
- 2026-09-14 — CLI `home-dns policy explain --group G DOMAIN…`.
- 2026-09-14 — Scripts and tests:
  - `scripts/blocklists/evaluate_policy.py`
  - compatibility catalog `tests/data/compatibility.yaml`
  - offline hostile-list regression tests
  - `network` real-policy test

### Changed — A3
- 2026-09-14 — Tripwire "entry covers protected" check uses a parent index: O(1) per entry and deterministic reports (was O(entries × protected)).

### Changed — A2 parameter decisions (owner-approved 2026-09-13)
- 2026-09-13 — Sanity limits configured for `hagezi-multi-pro` (180k–280k, ±5 %) and `hagezi-tif-mini` (140k–225k, +12 %/−8 %) as review thresholds.
- 2026-09-13 — Invalid-rule hard guard lowered from 5 % to 1 %.
- 2026-09-13 — Artifact store keeps exactly three versions (`current`, `previous`, `backup`). Older artifacts and leftover temp files are pruned only after the new state is written. `blocklists status` shows `backup`.
- 2026-09-13 — Tests prove `--accept-anomalies` never bypasses protected-domain, malformed-data, safety-validation, test-deployment or health-check gates.
- 2026-09-13 — Plan: A5 stale-mirror escalation (warning, warning, critical; reset on valid update) and a ≥ 30-day re-measurement before C3.

### Changed
- 2026-09-13 — `groups.yaml` no longer holds devices; device assignments move to backend storage (A7).
- 2026-09-13 — Removed `dashboard/backend/` and `dashboard/shared/`; the backend lives in `src/home_dns/api/`.
- 2026-09-13 — `config/storage/storage.yaml` no longer defines paths; paths are application settings.
- 2026-09-13 — `.env.example` uses `HOME_DNS_*` variable names.

### Not done (by design)
- No DNS software installed. No DNS, DHCP, IPv4, IPv6, firewall, router or service changes. No blocklists enabled. No dashboard deployed.

### Added — RAM/tmpfs audit (before A5, 2026-09-14)
- 2026-09-14 — Focused audit of every disk write in the codebase to decide whether a dedicated
  RAM-backed temporary-storage subsystem is justified. **Conclusion: no** — `paths.tmp_dir` was
  already tmpfs-ready by construction; documented in `docs/specs/a4-storage-maintenance.md` §12
  and ADR 0007's amendment.
- 2026-09-14 — Two small fixes surfaced by the audit: `storage backup`'s SQLite snapshot staging
  is now cleaned up even if `create_backup` raises; `StorageReport` gained a non-mutating
  `tmp_dir_usable` health signal, shown by `storage status`.
- 2026-09-14 — Tests: 12 new (845 total), coverage 97.80%.

