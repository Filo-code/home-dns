# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Dates are ISO 8601.

## [Unreleased]

### Added
- 2026-09-13 — Documentation-based comparison of Pi-hole + Unbound, AdGuard Home and Technitium DNS Server (`docs/architecture-comparison.md`).
- 2026-09-13 — ADR 0001: Pi-hole v6 + Unbound, *approved for implementation planning — pending Raspberry Pi audit and final Fastweb Seven network validation* (`docs/adr/0001-dns-architecture.md`).
- 2026-09-13 — Initial project scaffold: documentation placeholders, configuration templates (no deployable values), directory structure, `.gitignore`, `.env.example`.
- 2026-09-13 — Interim network snapshot (`docs/audits/2026-09-13-interim-network-snapshot.md`).

### Not done (by design)
- No DNS software installed. No DNS, DHCP, IPv4, IPv6, firewall, router or service changes. No blocklists enabled. No dashboard deployed.
