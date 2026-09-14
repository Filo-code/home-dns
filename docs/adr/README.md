# Architecture Decision Records

Each important decision gets one ADR explaining the **decision, alternatives, reasoning and consequences** (CLAUDE.md §52).
ADRs are never deleted. A changed decision is recorded in a **new** ADR that supersedes the old one.

| ADR | Title | Status |
|---|---|---|
| [0001](0001-dns-architecture.md) | DNS architecture: Pi-hole v6 + Unbound | Approved for implementation planning — pending Raspberry Pi audit and final Fastweb Seven network validation |
| [0002](0002-software-stack.md) | Software stack and tooling | Accepted |
| [0003](0003-configuration-model.md) | Filtering configuration model | Accepted |
| [0004](0004-blocklist-pipeline.md) | Blocklist pipeline | Accepted |
| 0005 | Backend and dashboard architecture | Not yet written (A7) |
| 0006 | Telegram alerting | Not yet written (A6) |
| 0007 | Storage strategy | Not yet written (A4; paths finalised after B1) |
| 0008 | IPv6 strategy | Not yet written (D3, after Fastweb Seven audit) |

Planned numbers follow [../implementation-plan.md](../implementation-plan.md) and may shift if new decisions come up.

Status values: `Proposed` · `Approved for implementation planning` · `Accepted` · `Under review` · `Superseded by NNNN` · `Rejected`.
