# A4 — Storage and Maintenance: Design

- **Status:** implemented 2026-09-14
- **Related:** [ADR 0007](../adr/0007-storage-strategy.md) · [ADR 0004](../adr/0004-blocklist-pipeline.md) (artifact retention, reused unchanged) · [implementation-plan.md](../implementation-plan.md)
- **Constraints:** offline and development only. No Raspberry Pi, router, network or production changes. No Docker. No destructive changes on the development machine.

## 1. What already exists (A0–A3) — not duplicated

| Existing | Where | A4 relationship |
|---|---|---|
| Content-addressed blocklist artifact store, `current`/`previous`/`backup` retention, atomic writes, dry-run default, prune-only-after-durable-state-write | `storage/artifacts.py` | **Reused unchanged.** A4 adds one small, purely additive method (`reconcile`, §5) and treats the store as one storage category to report on |
| SQLite connection setup (WAL, `foreign_keys`, `busy_timeout`) + versioned migrations | `storage/sqlite.py` | **Extended, not replaced.** A4 adds backup/integrity/checkpoint/vacuum primitives to the same module, because the architecture already restricts `sqlite3` imports to this package (`tests/architecture/test_boundaries.py::test_sqlite3_is_only_used_by_storage`) |
| Configurable `paths.data_dir` / `paths.log_dir` / `paths.backup_dir`, placeholder-capable, resolved relative to the project root | `config/settings.py`, `config/loader.py` | **Extended** with `paths.tmp_dir` (§2), following the exact same pattern |
| One schema-owning loader per config concern (`config/filtering.py` for `config/{groups,policies,rules,blocklists,protected-domains}`) | `config/filtering.py` | **Pattern reused.** A4 adds `config/storage.py` for `config/storage/storage.yaml`, the same way |
| `validate-config` reports a per-concern summary and excludes schema-owned files from the generic scan | `cli.py` | **Extended** with a storage summary section, the same way filtering was added in A1 |
| Dry-run-by-default mutating functions, atomic temp-file-then-rename writes, content hashing for integrity | `storage/artifacts.py` | **Pattern reused** by every new storage module |
| Package boundaries (`storage` must not import `config`/`providers`/`api`/`bootstrap`/`cli`; only `storage` may import `sqlite3`) | `tests/architecture/test_boundaries.py` | **Unchanged and respected.** No new top-level package: all new I/O modules live under `storage/`, so no new boundary rules are needed |

No new top-level package is introduced. A `maintenance` package was considered and rejected (§8): the existing `storage` package boundary already fits everything A4 needs, and one more package would duplicate the "orchestration layer for I/O the CLI composes" role that `pipeline` already fills for blocklists.

## 2. Storage paths (extends `PathsSettings`)

| Setting | Existing? | Holds |
|---|---|---|
| `paths.data_dir` | yes | Blocklist artifacts (`data_dir/blocklists/…`, owned by A2), SQLite database file (future A7 data) |
| `paths.log_dir` | yes | Application log files |
| `paths.backup_dir` | yes | Backup bundles (§6) |
| `paths.tmp_dir` | **new** | Transient files: in-progress downloads, staging before an atomic rename, anything that must not survive a crash as "real" data |

`tmp_dir` follows the exact rules already established for the other three: `Deferred[Path]`, relative paths are `dev_only` (an error in production), and it is resolved with the existing `LoadedConfig.resolve()`. On the Pi, a natural production choice is a `tmpfs` mount for `tmp_dir` (zero SD-card writes for transient state) — this is a deployment decision for C-stage, not a code change: the path is just configuration.

## 3. Storage categories

| # | Category | What | Where | Deletable automatically? |
|---|---|---|---|---|
| 1 | Blocklist artifacts | Rendered lists + metadata | `data_dir/blocklists/<source>/artifacts/` | Only `current`/`previous`/`backup` are kept; older ones are pruned by A2's `activate()` and by the new `reconcile()` (§5). **`current` is never deletable** |
| 2 | Application database | SQLite file + `-wal`/`-shm` | `data_dir/<name>.db` | Never deleted automatically. Only backed up, checked and checkpointed (§7) |
| 3 | Logs | Rotated application log files | `log_dir/` | Bounded by rotation (size × count), not by an unattended delete sweep (§4) |
| 4 | Temporary files | In-progress downloads, staging areas | `tmp_dir/` | Swept by age; only direct children of `tmp_dir`, never recursively, never symlinks (§4) |
| 5 | Backups | Verified, versioned bundles | `backup_dir/backup-<timestamp>/` | Oldest pruned beyond the retention count; **the newest valid backup is never deletable**, even if retention is misconfigured to 0 (§6) |

## 4. Cleanup safety

**Invariant, enforced by construction, not by convention:** a cleanup action only ever touches files it can prove belong to a registered category, by one of:
- a content-addressed name it computed itself (artifacts, already true from A2);
- a filename pattern it defined itself (`backup-<UTC timestamp>`, mirroring the artifact store's own hash-pattern guard);
- direct (non-recursive) children of a single configured directory, with symlinks refused and any path that resolves outside that directory refused (temp sweep).

Nothing is ever deleted by glob, by age alone across an arbitrary tree, or by trusting a path that came from outside the module.

**Idempotency:** every cleanup primitive computes "what would be removed" first (from durable state, not from a mutable counter), and removing an already-removed file is a no-op (`missing_ok=True` / a guarded existence check), so running cleanup twice — or being interrupted between "compute" and "remove" and run again — produces the same end state.

**Crash ordering** (already the rule for artifacts, applied to backups too): write new data → verify it → make it durable (atomic rename of the *new* thing) → only then delete anything superseded. A crash before the rename leaves the previous state fully intact; a crash after leaves the new state intact with possible orphaned temp files, cleaned up by the next run.

## 5. Blocklist artifact retention (unchanged from A2)

A2's policy — `current` / `previous` / `backup`, pruned only after the new `state.json` is durably written — is **not modified**. A4 adds one purely additive method:

```python
def reconcile(self, source_id: str, *, dry_run: bool = True) -> StoreChange
```

It prunes anything not referenced by the *current on-disk state* (leftover temp files, orphaned shas from an interrupted run) **without activating anything and without changing the state**. This closes the one gap A2 left open: if a source is never updated again after an interrupted run, its orphans would otherwise sit until the next successful `activate()`. `reconcile` lets scheduled cleanup (§9, C-stage) reclaim them proactively. It reuses the exact same `_prunable`/`_prune` internals as `activate()`, so there is no new deletion logic to get wrong.

Regression tests (§12) prove: `current` is never removed by any A4 code path, `previous` and `backup` survive reconciliation, rollback still works after a reconcile, and an interrupted cleanup (simulated crash mid-prune) leaves every referenced artifact intact.

## 6. Backups

| Question | Answer |
|---|---|
| What is backed up | Named, caller-supplied sources (a logical name → a real path). In A4's scope: the `config/` tree and a hot SQLite snapshot when a database exists. Device mappings and dashboard configuration are A7 scope and will be added as more named sources then, with no change to the backup mechanism |
| Where | `backup_dir/backup-<UTC timestamp>/`, one directory per backup, plus `manifest.json` inside it |
| Format | Plain file copies (not an archive), so a single corrupted file is still individually detectable and, if needed, individually recoverable. No compression in A4 — a documented, deliberate simplification (§11) |
| Integrity | Every file's SHA-256 is recorded in the manifest at creation and re-verified on `verify`/`restore`. A backup directory without a valid `manifest.json` is treated as incomplete, reported, and never trusted |
| Atomicity | Written to `backup_dir/.backup-<timestamp>.tmp/`, then `os.replace()`d into its final name — a single atomic directory rename. `manifest.json` is written last, so a crash mid-copy never produces a directory that looks complete |
| Retention | Newest N kept (`retention.backups_keep`, §9), oldest pruned. Only directories matching the `backup-<timestamp>` pattern this module produces are ever candidates. **The single newest *valid* backup is never pruned**, even if `backups_keep` is misconfigured to 0 |
| Restore | Verifies every checksum first; refuses to restore anything if verification fails. Dry-run by default, reports what would be restored where |
| Restore is tested, not assumed | A real backup → restore round trip is a test (§12), asserting byte-for-byte identical content, not just "no exception" |

## 7. SQLite strategy

No concrete schema exists yet (A7 will add repositories); A4 defines the *policy* and the *primitives*, extending `storage/sqlite.py`:

| Concern | Decision | Why |
|---|---|---|
| Live backup | `sqlite3.Connection.backup()` (the online backup API) into a temp path, not a raw file copy | A raw copy of a WAL-mode database can capture an inconsistent snapshot mid-write; the backup API is the documented safe way to copy a live database |
| Integrity check | `PRAGMA quick_check` by default; `PRAGMA integrity_check` available as an explicit, slower option | `quick_check` catches structural corruption without the full page-by-page scan cost of `integrity_check`, which matters on SD-card I/O |
| WAL checkpoint | `PRAGMA wal_checkpoint(PASSIVE)` exposed as an explicit action; `TRUNCATE` available but not automatic | Reclaims WAL file space without blocking writers (`PASSIVE`); `TRUNCATE` is more aggressive and is left as a manual/future-scheduled action, not something A4 runs unattended |
| `VACUUM` | Implemented, but **never called automatically anywhere in this codebase** | `VACUUM` rewrites the entire database file. On a microSD card that is a large, avoidable write-amplification event for uncertain benefit. It stays available for a rare, deliberate, manually-invoked maintenance action if fragmentation is ever *measured* to be a real problem — never a scheduled job |
| Retention | `retention.query_history_days` (default ~30, per CLAUDE.md §16) is a **policy value** for A4 to define and validate; the row-level deletion logic belongs to whichever component owns the query-history table (A7) | A4's job is the storage-safety policy, not the query-history schema, which doesn't exist yet |

## 8. Logs

| Decision | Detail |
|---|---|
| Bounding mechanism | Size- and count-bounded rotation (`logging.handlers.RotatingFileHandler`, `maxBytes` × `backupCount`), not day-based rotation | A single very chatty day can still fill a day-bounded log; a byte cap cannot overflow regardless of write volume |
| What's retained | Every WARNING and above indefinitely within the rotation window (the newest N × maxBytes); routine INFO/DEBUG is the first to roll off | Security/audit signal (failed auth, tripwire hits, failed deployments) must survive; routine noise is what rotation exists to bound |
| journald (C-stage) | Out of scope for A4 code — systemd's own `SystemMaxUse=` bounds it at the OS level once services run on the Pi. Documented here so C-stage installation doesn't forget it | A4 is offline; there is no systemd service running yet to configure |
| SD-card writes | `tmp_dir` on a future `tmpfs` mount removes transient-file writes entirely from the SD card (§2); log writes remain the main ongoing write source and are bounded by rotation, not eliminated | Logs are the one category that must exist and accumulate some writes by nature; bounding, not eliminating, is the correct target |

## 9. Storage thresholds and retention (configurable, not hard-coded)

New loader `config/storage.py` for `config/storage/storage.yaml` (schema-owned, like `config/filtering.py`), producing two pure models in `core/storage.py`:

```yaml
disk_usage_thresholds_percent:
  healthy_below: 70
  warning_from: 70
  auto_cleanup_from: 80
  emergency_cleanup_and_alert_above: 90

retention:
  logs_max_bytes: 10485760     # 10 MiB per log file
  logs_backup_count: 5         # -> 50 MiB bound per log stream
  temp_max_age_hours: 24
  backups_keep: 7
  query_history_days: 30
```

Threshold bands (boundaries match the owner-approved policy exactly):

| Band | Range | Automatic action |
|---|---|---|
| `HEALTHY` | `< warning_from` | none |
| `WARNING` | `[warning_from, auto_cleanup_from)` | none — observe and report only |
| `AUTO_CLEANUP` | `[auto_cleanup_from, emergency_from)` | routine cleanup: temp sweep at the configured age, backup retention enforced, artifact reconciliation |
| `EMERGENCY` | `>= emergency_from` | everything `AUTO_CLEANUP` does, plus an aggressive temp sweep (age limit ignored) and backup retention tightened to 1 — **never below 1**, and `current` artifacts / the live database are never touched |

`classify_usage()` is pure and total: every percentage in `[0, 100]` maps to exactly one band, tested at every boundary (§12).

## 10. Crash and interruption safety

Every mutating primitive follows write → verify → atomically publish → prune-superseded, and every one is tested with a simulated failure injected at the boundary between "new state durable" and "old state removed" (monkeypatching the delete step to raise). The required outcome, proven by test in every case: **the last known-good state remains fully readable**, and nothing referenced by durable state is ever missing.

## 11. Future USB SSD support

Not implemented in A4, by design (§2 already makes it a non-event):
- Every category's location is a configured `Path` (`data_dir`, `log_dir`, `backup_dir`, `tmp_dir`), resolved once at startup.
- No module hard-codes a filesystem location; storage code receives paths as parameters.
- Moving `data_dir` (and, later, `log_dir`) to a USB SSD mount is a configuration change (and a documented `rsync` + remount procedure in C-stage), not a code change.

## Deliberate simplifications (owner can revisit)

| Simplification | Ceiling | Upgrade path |
|---|---|---|
| Backups are uncompressed file copies | More disk per backup than a compressed archive | Add optional gzip per file if backup-directory size becomes a measured problem |
| Query-history row deletion policy is a value only (`retention.query_history_days`), not enforced by any code yet | No table exists to enforce it against | A7 implements the deletion query against its own schema, reading this same config value |
| `wal_checkpoint(TRUNCATE)` and `VACUUM` are manual-only, no CLI flag | An operator must invoke them via a Python shell/script, not a documented command | Add a guarded CLI flag if C-stage operations show a real need |
