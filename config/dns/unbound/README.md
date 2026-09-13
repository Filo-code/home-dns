# Unbound configuration (planned)

> **Status: not written.** Unbound is **not installed** (ADR 0001).

- Starting point: the official Pi-hole guide (https://docs.pi-hole.net/guides/dns/unbound/), reviewed against the Unbound manual in Phase 6.
- **This directory must be included in backups.** Pi-hole Teleporter does not cover Unbound (ADR 0001 T2).
- A DoT-forwarding fallback profile will be documented if the Fastweb Seven intercepts port 53 (ADR 0001 T9, gate G5).
