# Blocklists

> **Status:**
> - The A2 pipeline is implemented and tested offline.
> - **Nothing is deployed to any DNS server.**
> - Activation is local-only (development) and is refused until protected domains exist (A3).
> - Design: [ADR 0004](adr/0004-blocklist-pipeline.md). Evidence: [measurements](research/2026-09-13-hagezi-measurements.md).

## Approved lists

| Id | List | Primary | Fallback | Freshness |
|---|---|---|---|---|
| `hagezi-multi-pro` | HaGeZi Multi PRO | jsDelivr | GitHub raw | 48 h |
| `hagezi-tif-mini` | HaGeZi TIF Mini | jsDelivr | GitHub raw | 48 h |

- **Catalog:** `config/blocklists/sources.yaml`.
- **Adding a list** requires a documented reason and an explicit owner decision.

## What happens on an update

For each source:
1. **Download and validate** the primary. Every step must pass: download, HTTP 200 + `text/plain` + not HTML + UTF-8, size, format + `Last modified` within 48 h, parse, normalization, deduplication + declared entry count.
2. **Fallback:** if any step fails or the list is stale, try the fallback the same way.
3. **Nothing acceptable:** if neither mirror is acceptable, **keep the currently active list** and raise a warning.
4. **Remaining checks** on the accepted download: protected-domain tripwire (hard gate), artifact syntax validation, sanity, test deployment on an isolated mock, health check.
5. **Activation:** only with `--apply`.

## Commands (development machine)

```bash
# Dry-run: download (needs Internet), validate, test-deploy to a mock. Writes nothing.
PYTHONPATH=src uv run --locked python -m home_dns.cli blocklists update

# One source, JSON report
PYTHONPATH=src uv run --locked python -m home_dns.cli blocklists update --source hagezi-tif-mini --format json

# Activate in the local artifact store (.local/data/blocklists, git-ignored).
# Refused until protected domains exist (A3).
PYTHONPATH=src uv run --locked python -m home_dns.cli blocklists update --apply

# After manually reviewing an anomaly (never bypasses the tripwire)
PYTHONPATH=src uv run --locked python -m home_dns.cli blocklists update --apply --accept-anomalies

# Inspect and roll back (rollback is dry-run unless --apply)
PYTHONPATH=src uv run --locked python -m home_dns.cli blocklists status
PYTHONPATH=src uv run --locked python -m home_dns.cli blocklists rollback hagezi-multi-pro --apply
```

Exit codes:

| Code | Meaning |
|---|---|
| `0` | every source `activated` / `would_activate` / `unchanged` |
| `1` | any source kept previous, held for review, blocked or failed; or rollback refused; or production environment |
| `2` | configuration error or unknown source |

## Outcomes

| Outcome | Meaning | What to do |
|---|---|---|
| `would_activate` | Dry-run passed | Run with `--apply` when appropriate |
| `activated` | New artifact is current; old one is `previous` | Nothing |
| `unchanged` | Same content as the active artifact | Nothing |
| `kept_previous` | No mirror delivered an acceptable list | Read the per-attempt reasons; retry later; check the mirrors |
| `held_for_review` | Change outside the approved sanity limits | Inspect `added` / `removed` in the report; if legitimate, rerun with `--accept-anomalies` |
| `blocked_by_tripwire` | The list would block a protected domain, or no protected domains exist | **Do not bypass.** Report the entry upstream or fix the protected-domain data |
| `failed` | Artifact, test deployment, health check or activation failed | Read the failing step; the previous artifact is still active |

## Measuring lists (research)

```bash
PYTHONPATH=src uv run --locked python scripts/blocklists/measure_sources.py --since 2026-08-13 --cache-dir /tmp/measure
uv run --locked pytest -m network tests/blocklists     # real lists through the pipeline (dry-run)
```

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `stale: last modified …h ago` on both mirrors | Upstream has not published in 48 h, or both mirrors are cached |
| `header declares N entries, found M` | Truncated download |
| `body looks like HTML` / `unexpected content type` | Captive portal, error page or wrong URL |
| `no protected domains configured` | Expected until A3 |
