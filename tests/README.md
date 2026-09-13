# tests/

Automated tests (CLAUDE.md §42–§43). Run with `make test`. Rules: [../docs/development.md](../docs/development.md#testing-rules).

| Directory | Covers | Since |
|---|---|---|
| `unit/` | config (placeholders, loader, readiness, filtering loader), core (models, domains, filtering checks), providers, storage, bootstrap, CLI | A0–A1 |
| `contract/` | `DnsProvider` contract: the same tests for every provider (mock now, Pi-hole v6 in C2) | A0 |
| `api/` | backend HTTP API | A0 |
| `architecture/` | package import boundaries; no real IPs/MACs in code or config | A0 |
| `dns/` | resolution, DNSSEC, IPv4/IPv6, cache, blocked/allowed/protected/local domains | C1 |
| `security/` | malware, phishing, tracker, ad, gambling, adult (safe, documented test domains only) | A3 |
| `compatibility/` | Windows, Android, iOS/iPadOS, Smart TV, Xbox, streaming, social networks | A3 / D |
| `blocklists/` | real-list tests marked `network` (excluded from `make test`); offline pipeline tests live in `unit/pipeline/` | A2 |
| `dashboard/` | end-to-end browser tests (unit tests live next to the frontend code) | A8 |

The rule "measure before and after major changes; do not optimise prematurely" still applies.
