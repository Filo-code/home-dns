# Restore

> **Status:** implemented and tested offline (A4). Design:
> [specs/a4-storage-maintenance.md §6](specs/a4-storage-maintenance.md#6-backups) · Decision:
> [ADR 0007](adr/0007-storage-strategy.md).

## What it does

Restores a named backup after verifying every file's checksum. If verification fails, **nothing is
restored** — the command refuses outright rather than restoring a possibly-corrupted mix of files.

## Why it exists

"A backup is not considered valid until restore is tested" (CLAUDE.md §33). This is the tested
half of that requirement: `tests/unit/storage/test_backup.py` proves a real backup → restore round
trip reproduces the original file byte-for-byte, and that a tampered or incomplete backup is
refused, not partially applied.

## Operation

```bash
PYTHONPATH=src uv run --locked python -m home_dns.cli storage restore backup-20260914T120000Z
PYTHONPATH=src uv run --locked python -m home_dns.cli storage restore backup-20260914T120000Z --apply
```

Dry-run (the default) reports which files would be restored, without writing anything.

## How it works

1. `verify_backup` recomputes every file's SHA-256 and compares it to the manifest.
2. If anything fails, the whole restore is refused: `restore refused: … verification failed …`.
3. Otherwise, each file is written via the same atomic temp-then-rename pattern used everywhere
   else in this codebase — a restore interrupted mid-file leaves the previous file in place, not a
   half-written one.

## Troubleshooting

| Symptom | Meaning |
|---|---|
| `restore refused: … no such file` | The backup name doesn't exist under `paths.backup_dir`; check `storage status` or list the directory |
| `restore refused: … verification failed` | The backup is corrupted or was modified outside this tool. Use an earlier backup instead |

## Recovery

If a restore is interrupted partway through, re-running the same restore command is safe: each
file is independently verified and atomically written, so a partially-completed restore simply
finishes the remaining files on the next run.

## Rollback

Restoring is itself the rollback mechanism for configuration. There is no separate "undo a
restore" — take a fresh backup before restoring if you want to be able to return to the
pre-restore state.

## Security implications

Restore only writes into caller-specified target paths; it never restores outside those, and it
never restores anything that fails checksum verification.
