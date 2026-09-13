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

### Changed
- 2026-09-13 — Removed `dashboard/backend/` and `dashboard/shared/`; the backend lives in `src/home_dns/api/`.
- 2026-09-13 — `config/storage/storage.yaml` no longer defines paths; paths are application settings.
- 2026-09-13 — `.env.example` uses `HOME_DNS_*` variable names.

### Not done (by design)
- No DNS software installed. No DNS, DHCP, IPv4, IPv6, firewall, router or service changes. No blocklists enabled. No dashboard deployed.
