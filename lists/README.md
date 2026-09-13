# lists/

Blocklist and allowlist **sources and metadata** by category. Downloaded list contents are not committed.

> **No list is enabled.** Candidates are evaluated in Phase 8 (core) and Phase 9 (Italian).

| Directory | Scope | Initial candidates |
|---|---|---|
| `core/` | Ads, trackers, general protection | HaGeZi Multi PRO: catalogued in `config/blocklists/sources.yaml` |
| `malware/`, `phishing/` | Threat intelligence | HaGeZi TIF Mini: catalogued in `config/blocklists/sources.yaml` |
| `italian/` | Italian ads/trackers | To be researched |
| `telemetry/` | Telemetry | To be researched; high false-positive risk for TV/Xbox |
| `gambling/`, `adult/` | Content categories | To be researched; per-group only |

Every list must pass the pipeline in CLAUDE.md §19 (download → validate → normalize → deduplicate → protected-domain scan → syntax check → sanity check → test → deploy → health check).
