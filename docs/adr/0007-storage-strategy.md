# ADR 0007: Storage and Maintenance Strategy

| Field | Value |
|---|---|
| **Status** | Accepted |
| Date | 2026-09-14 |
| Decision owner | Project owner (A4 scope and constraints, 2026-09-14) |
| Related | [ADR 0004](0004-blocklist-pipeline.md) (artifact retention, reused unchanged) · [A4 design](../specs/a4-storage-maintenance.md) · [implementation-plan.md](../implementation-plan.md) |

## Context

CLAUDE.md §16–§17 requires the system to never silently fill its storage, with owner-approved
thresholds (healthy < 70%, warning 70–80%, automatic cleanup 80–90%, emergency cleanup + critical
alert above 90%) and storage paths that make a future microSD → USB3 SSD migration a configuration
change, not a rewrite. A2 already built one piece of this — content-addressed blocklist artifact
retention (`current`/`previous`/`backup`) — but nothing yet covered the database, logs, temporary
files, backups, or the thresholds themselves.

## Decision

1. **No new top-level package.** Everything lives under the existing `storage/` package
   (`disk.py`, `tempfiles.py`, `logs.py`, `backup.py`, `report.py`, `cleanup.py`, plus additions to
   `artifacts.py` and `sqlite.py`), which already owns I/O and dry-run-by-default mutation. A
   `maintenance` package was considered and rejected: it would duplicate the role `storage`
   already fills.
2. **Pure decisions, separate from I/O.** `core/storage.py` holds thresholds, retention policy,
   band classification (`classify_usage`) and cleanup planning (`plan_cleanup`) as pure functions
   over plain data — no filesystem access — the same split already used for blocklists
   (`core.blocklists` decides, `pipeline` and `storage.artifacts` do).
3. **A2's artifact retention is reused unchanged.** The only addition is `ArtifactStore.reconcile()`,
   which prunes orphans without activating anything, reusing A2's own internals.
4. **A fourth configurable path, `paths.tmp_dir`**, added the same way as the existing three
   (`data_dir`, `log_dir`, `backup_dir`): `Deferred[Path]`, relative paths flagged `dev_only` in
   production, resolved via the existing `LoadedConfig.resolve()`.
5. **Thresholds and retention are configuration, not code.** `config/storage/storage.yaml` gets its
   own schema-owning loader, `config/storage.py`, following the exact pattern A1 established for
   filtering config. Band boundaries: `< warning_from` healthy, `[warning_from, auto_cleanup_from)`
   warning (observe only), `[auto_cleanup_from, emergency_from)` auto-cleanup, `>= emergency_from`
   emergency.
6. **Backups are plain, checksummed file copies**, atomically published (temp directory + one
   `os.replace`), never an archive format — simpler to verify per-file and partially recover from.
   Retention keeps the newest N; the single newest *valid* backup can never be pruned.
7. **SQLite gets a documented, restrained policy**, extending `storage/sqlite.py` (the only module
   allowed to import `sqlite3`, per the existing architecture test): the online backup API for
   live copies, `quick_check` by default for integrity, `wal_checkpoint(PASSIVE)` as the routine
   option, and `VACUUM` implemented but **never called automatically anywhere in this codebase** —
   proven by a regression test that greps `src/` for any automatic call site.
8. **Logs are bounded by size × count** (`RotatingFileHandler`), not by day, so a single chatty
   period cannot overflow storage regardless of how much it logs.
9. **New CLI commands**, dry-run by default: `home-dns storage status`, `cleanup [--apply]`,
   `verify`, `backup [--apply]`, `restore <name> [--apply]`. Refused in production, matching every
   other A-stage command.

## Alternatives considered

| Alternative | Why not |
|---|---|
| A separate `maintenance` package for cleanup/backup orchestration | Would duplicate the role `storage` (I/O + dry-run mutation) already has; more package boundaries to maintain for no isolation benefit |
| Day-based log rotation (`TimedRotatingFileHandler`) | A single very chatty day can still fill the disk; a byte cap cannot, regardless of volume |
| Compressed backup archives (tar.gz) | Harder to verify or recover a single file from; adds a dependency decision for a benefit not yet measured to be needed |
| Scheduled/automatic `VACUUM` | Full-file rewrite is a large, avoidable SD-card write-amplification event; kept as a manual-only primitive |
| Raw file copy for database backups | Can capture an inconsistent snapshot of a live WAL-mode database; the SQLite online backup API is the documented safe method |
| Age-based (not count-content-addressed) blocklist-artifact cleanup | A2's `current`/`previous`/`backup` policy, approved by the owner, is reused unchanged rather than replaced |

## Consequences

- **Bounded disk use across every category**, each independently: artifacts (3 versions,
  unchanged), backups (N newest, minimum 1), logs (size × count), temp files (age-based sweep,
  aggressive during emergency).
- **A5 gets a ready-made status model.** `core.storage.StorageReport` (disk usage, band, per-
  category bytes, last backup age, artifact counts, recommended action) is the exact "clean
  interface" A5's monitoring is expected to consume; A4 raises no alerts itself.
- **SSD migration stays a configuration change.** All four path settings are resolved once, at
  startup, from configuration; no storage module hard-codes a location.
- **Nothing in A4 required a Pi, network or production change.** Real filesystem operations were
  exercised only against the development machine's own filesystem, under `tmp_path`/scratch
  directories, in tests.
