# Architecture Decision Records

Each important decision gets one ADR explaining the **decision, alternatives, reasoning and consequences** (CLAUDE.md §52).
ADRs are never deleted. A changed decision is recorded in a **new** ADR that supersedes the old one.

| ADR | Title | Status |
|---|---|---|
| [0001](0001-dns-architecture.md) | DNS architecture: Pi-hole v6 + Unbound | Approved for implementation planning — pending Raspberry Pi audit and final Fastweb Seven network validation |
| [0002](0002-software-stack.md) | Software stack and tooling | Accepted |
| [0003](0003-configuration-model.md) | Filtering configuration model | Accepted |
| [0004](0004-blocklist-pipeline.md) | Blocklist pipeline | Accepted |
| [0005](0005-backend-dashboard.md) | Backend and dashboard architecture | Accepted |
| [0006](0006-telegram-alerting.md) | Telegram alerting | Accepted |
| [0007](0007-storage-strategy.md) | Storage and maintenance strategy | Accepted |
| 0008 | IPv6 strategy | Not yet written (D3, after Fastweb Seven audit) |
| [0009](0009-filtering-policy.md) | Filtering policy, protected domains and policy engine | Accepted (Light/Normal sanity limits pending approval) |
| [0010](0010-frontend-hosting.md) | Frontend hosting: Raspberry-Pi-served static SPA | Accepted |

Planned numbers follow [../implementation-plan.md](../implementation-plan.md) and may shift if new decisions come up.

Status values: `Proposed` · `Approved for implementation planning` · `Accepted` · `Under review` · `Superseded by NNNN` · `Rejected`.
