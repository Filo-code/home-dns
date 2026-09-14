# Maintenance

> **Status:** cleanup safety implemented and tested offline (A4). Scheduled jobs and the safe
> update process are C-stage (the Pi doesn't exist yet in this repository's scope).
> Design: [specs/a4-storage-maintenance.md](specs/a4-storage-maintenance.md) · Decision:
> [ADR 0007](adr/0007-storage-strategy.md).

## What it does

Runs the cleanup appropriate for the current storage band (see [storage.md](storage.md)) safely:
idempotently, dry-run by default, and provably unable to remove anything outside a registered
category.

## Why it exists

Pi-hole has no native rollback (ADR 0001 T3): a pre-update snapshot and a tested rollback
procedure are required before any update on the real Pi. That snapshot is this subsystem's backup
mechanism (see [backups.md](backups.md)); the cleanup half keeps the SD card from filling between
updates.

## Cleanup safety

Every cleanup action only touches files it can prove belong to a registered category, by one of:

- a content-addressed name it computed itself (blocklist artifacts, unchanged from A2);
- a filename pattern it defined itself (`backup-<UTC timestamp>`);
- direct (non-recursive) children of one configured directory, with symlinks refused and any
  path resolving outside that directory refused (temporary files).

Nothing is ever deleted by a bare glob, by age alone across an arbitrary tree, or by trusting a
path from outside the module. Every mutating function defaults to `dry_run=True`; running cleanup
twice, or being interrupted mid-run, produces the same end state (idempotent) — proven by tests
that inject a failure between "new state durable" and "old state removed" and assert the last
known-good state stays fully readable.

## Dependencies

`home_dns.core.storage` (thresholds, planning) · `home_dns.storage.{disk,tempfiles,backup,
artifacts,report,cleanup}` · `config/storage/storage.yaml`.

## Configuration

See [storage.md](storage.md#configuration).

## Operation

```bash
PYTHONPATH=src uv run --locked python -m home_dns.cli storage cleanup            # dry-run
PYTHONPATH=src uv run --locked python -m home_dns.cli storage cleanup --apply    # perform it
```

## Troubleshooting

| Symptom | Meaning |
|---|---|
| `state=healthy action=none` | Nothing to do; this is the expected steady state |
| A backup you expected to survive was pruned | Check `retention.backups_keep`; the single newest *valid* backup is the only one guaranteed to survive |

## Recovery

If cleanup is interrupted (process killed, power loss), re-running it is always safe: it recomputes
what needs removing from durable state, not from an in-memory counter.

## Rollback

Cleanup has no "undo" beyond restoring from backup (see [restore.md](restore.md)) — it only ever
removes disposable or superseded data, never the current, active copy of anything.

## Security implications

Cleanup and reconciliation never read file *contents* for anything other than SHA-256 verification
(backups, artifacts); no secrets are handled by this subsystem.
