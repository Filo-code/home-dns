# Monitoring configuration (planned)

> **Status: not written.** Filled in Phase 12. Numeric thresholds (latency, CPU, RAM, temperature) come from the Raspberry Pi resource baseline (ADR 0001 gate G2), not from guesses.

Must monitor independently (ADR 0001 T1):
- `pihole-FTL` service and DNS answers on port 53
- `unbound` service and recursive resolution / DNSSEC validation

Recovery flow (CLAUDE.md §32): detect → retry → backoff → recover if safe → verify → notify. No infinite restart loops.
