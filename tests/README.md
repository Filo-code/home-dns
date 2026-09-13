# tests/

Automated tests (CLAUDE.md §42–§43). **Empty until the relevant phase.**

| Directory | Covers |
|---|---|
| `dns/` | Resolution, DNSSEC, IPv4/IPv6, cache, blocked/allowed/protected/local domains |
| `security/` | Malware, phishing, tracker, ad, gambling, adult. Safe, documented test domains only |
| `compatibility/` | Windows, Android, iOS/iPadOS, Smart TV, Xbox, streaming, social networks |
| `blocklists/` | Pipeline, tripwire, syntax, sanity checks |
| `api/` | Pi-hole API contract tests (catch breaking changes on upgrade) |
| `dashboard/` | Backend and frontend tests |

Performance rule: measure before and after major changes. Do not optimise prematurely.
