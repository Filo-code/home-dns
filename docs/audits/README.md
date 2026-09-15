# Audits

Read-only audit results. Audits never change the system.

| Audit | File | Status |
|---|---|---|
| Interim network snapshot (pre-Fastweb Seven) | [2026-09-13-interim-network-snapshot.md](2026-09-13-interim-network-snapshot.md) | ✅ Done (passive, from a LAN client) |
| Raspberry Pi audit + resource baseline (B1, gates G1–G2) | [2026-09-14-b1-raspberry-pi-audit.md](2026-09-14-b1-raspberry-pi-audit.md) | ✅ Done — gate status formally updated in ADR 0001 at B3 |
| Fastweb Box Seven network audit (B2, gates G3–G5) | — | ⏳ Pending: Box Seven not yet active |
| Stage C lab installation: Pi-hole v6 + Unbound (not a passive audit — see scope note) | [2026-09-15-stage-c-pihole-lab.md](2026-09-15-stage-c-pihole-lab.md) | ✅ Pi-hole and Unbound installed and verified, chain working. LAN still on existing DNS — pending owner approval for rollout |
| PiholeV6Provider integration (not a passive audit — see scope note) | [2026-09-15-pihole-v6-provider.md](2026-09-15-pihole-v6-provider.md) | ✅ Implemented, unit-tested (31 tests), verified live against the lab Pi. Not wired into production (`serve` still development-only) |
