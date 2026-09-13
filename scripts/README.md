# scripts/

Operational scripts, grouped by purpose. **Empty by design until each phase.**

| Directory | Phase | Rule |
|---|---|---|
| `audit/` | 1–2 | Read-only. Never change the system |
| `install/`, `setup/` | 5–6 | Explain changes, risks and undo before running |
| `update/` | 12 | Check → backup → update → health check → DNS test → filtering test; roll back on failure |
| `blocklists/` | 8 | Protected-domain tripwire aborts deployment |
| `monitoring/`, `maintenance/` | 12 | Retry with backoff; no infinite restart loops |
| `backup/`, `restore/` | 16 | A backup is not valid until restore is tested |
| `tests/` | 7, 15 | Helper scripts for `tests/` |
