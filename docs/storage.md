# Storage

> **Status:** implemented and tested offline (A4). **Nothing is deployed.** Design:
> [specs/a4-storage-maintenance.md](specs/a4-storage-maintenance.md) · Decision:
> [ADR 0007](adr/0007-storage-strategy.md).

## What it does

Guarantees the system cannot silently fill its storage. It watches disk usage, classifies it into
a threshold band, and (from `auto_cleanup` upward) runs a bounded, safe cleanup across every
storage category — without ever touching the current blocklist artifacts, the live database, or
the single newest valid backup.

## Why it exists

CLAUDE.md §16–§17: a Raspberry Pi 4 with a 32 GB microSD must never run out of space silently, and
storage paths must be configurable enough that a future microSD → USB3 SSD migration is a
configuration change, not a rewrite.

## Storage categories

| Category | Where | Bounded by | Never auto-deleted |
|---|---|---|---|
| Blocklist artifacts | `paths.data_dir/blocklists/<source>/artifacts/` | A2's `current`/`previous`/`backup` retention (unchanged) | `current` |
| Application database | `paths.data_dir/home-dns.db` | Not deleted; only backed up/checked | the live file |
| Logs | `paths.log_dir/` | `RotatingFileHandler` (size × count) | — |
| Temporary files | `paths.tmp_dir/` | Age sweep (`retention.temp_max_age_hours`) | anything younger than the age limit; symlinks and subdirectories are never touched |
| Backups | `paths.backup_dir/backup-<timestamp>/` | `retention.backups_keep` newest kept | the single newest *valid* backup |

## Configuration

`config/storage/storage.yaml` (schema `config/storage.py`), values are never hard-coded:

```yaml
disk_usage_thresholds_percent:
  healthy_below: 70
  warning_from: 70
  auto_cleanup_from: 80
  emergency_from: 90
retention:
  logs_max_bytes: 10485760
  logs_backup_count: 5
  temp_max_age_hours: 24
  backups_keep: 7
  query_history_days: 30
```

Paths: `paths.data_dir`, `paths.log_dir`, `paths.backup_dir`, `paths.tmp_dir` in
`config/app/<env>.yaml` (see [development.md](development.md)).

## Threshold bands

| Band | Range | Action |
|---|---|---|
| `healthy` | `< warning_from` | none |
| `warning` | `[warning_from, auto_cleanup_from)` | none — observe and report only |
| `auto_cleanup` | `[auto_cleanup_from, emergency_from)` | routine cleanup: temp sweep at the configured age, backup retention enforced, blocklist artifacts reconciled |
| `emergency` | `>= emergency_from` | same as `auto_cleanup`, more aggressively: temp files swept regardless of age, backups pruned to the single newest valid one |

## Operation

```bash
# What's the current state?
PYTHONPATH=src uv run --locked python -m home_dns.cli storage status

# What would cleanup do right now? (dry-run is the default)
PYTHONPATH=src uv run --locked python -m home_dns.cli storage cleanup

# Actually run it
PYTHONPATH=src uv run --locked python -m home_dns.cli storage cleanup --apply

# Check backup checksums and blocklist artifact integrity
PYTHONPATH=src uv run --locked python -m home_dns.cli storage verify
```

Exit codes follow the project convention: `0` ok, `1` not ready / problems found, `2` configuration
error.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `unresolved path(s): tmp_dir` (or another path) | `paths.*` in the active profile is still an `<<AUDIT:…>>` placeholder |
| `storage commands are development-only …` | Running with `--env production`; storage commands, like blocklists, are gated until C3 |
| `verify` reports a backup mismatch | The backup directory was modified outside this tool; restore from an earlier valid backup, or re-create one |

## Recovery / Rollback

Nothing in this subsystem makes an irreversible change on its own: cleanup only removes files
inside the categories above, under the safeguards in [maintenance.md](maintenance.md#cleanup-safety).
To recover configuration, see [restore.md](restore.md).

## Security implications

Backup and restore operate entirely within `paths.*` directories the operator configures; no
secrets are read from or written into config files (enforced by the existing A0 hygiene check).
Storage commands are refused in production until C3, the same gate every other A-stage command has.
