# Backups

> **Status:** implemented and tested offline (A4). **Nothing is deployed.** Design:
> [specs/a4-storage-maintenance.md §6](specs/a4-storage-maintenance.md#6-backups) · Decision:
> [ADR 0007](adr/0007-storage-strategy.md).

## What it does

Creates verified, versioned, atomically-published backups of named source directories (in A4's
scope: the `config/` tree, plus a hot SQLite snapshot when a database exists), and can restore
them after verifying every checksum first.

## Why it exists

Backups must include Unbound configuration, because Pi-hole Teleporter does not (ADR 0001 T2). A
backup is not considered valid until restore is tested — this subsystem's own test suite proves a
real backup → restore round trip is byte-for-byte identical, not just "no exception".

## What is backed up

| Source | Included now | Added later |
|---|---|---|
| `config` | The whole `config/` tree | — |
| `database` | A hot SQLite snapshot via the online backup API, if `paths.data_dir/home-dns.db` exists | — |
| Device mappings, dashboard configuration | Not yet — no such data exists before A7 | A7 adds them as more named sources; the backup mechanism itself does not change |

## Where and how

`paths.backup_dir/backup-<UTC timestamp>/`, plus a `manifest.json` recording every file's SHA-256
and size. Written to a temp directory first and published with one atomic directory rename — an
interrupted backup can never look complete, and `list_backups` never surfaces it.

## Retention

Newest `retention.backups_keep` kept (default 7); the single newest *valid* backup is never
pruned, even if retention is misconfigured to 0.

## Integrity verification

Every file's checksum is re-verified on `verify` and before any `restore`. A backup directory
without a valid `manifest.json`, or with a checksum mismatch, is reported — never silently trusted,
never silently deleted.

## Operation

```bash
PYTHONPATH=src uv run --locked python -m home_dns.cli storage backup            # dry-run: what would be backed up
PYTHONPATH=src uv run --locked python -m home_dns.cli storage backup --apply    # write it
PYTHONPATH=src uv run --locked python -m home_dns.cli storage verify            # check all backups + artifacts
```

## Troubleshooting

| Symptom | Meaning |
|---|---|
| `backup 'backup-<ts>' already exists` | Two backups were requested within the same second; retry, or use a distinct timestamp |
| `verify` reports a mismatch | See [restore.md](restore.md) — never restore from a backup that fails verification |

## Security implications

Backups copy configuration files as-is. Since A0's hygiene check already rejects secret-like keys
in every config file, no secret should ever be present to back up in the first place; the backup
mechanism adds no new secret-handling surface.
