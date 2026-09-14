"""Bounded, safe cleanup of a single transient-files directory (``paths.tmp_dir``).

Only direct children of the configured directory are ever candidates for removal: no recursion,
no symlink traversal, and any entry that resolves outside the configured directory is refused
rather than deleted. This is deliberately conservative — a temp directory is not expected to have
subdirectories at all; if one appears, it is reported and skipped, not descended into.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class TempSweepResult:
    dry_run: bool
    removed: tuple[str, ...]
    skipped: tuple[tuple[str, str], ...]  # (name, reason)


def _is_contained(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def sweep_temp_dir(
    path: Path, *, max_age: timedelta, now: datetime, dry_run: bool = True
) -> TempSweepResult:
    """Remove direct-child files of ``path`` older than ``max_age``. Idempotent: an already-gone
    file is simply not seen on the next call, never an error."""
    if not path.is_dir():
        return TempSweepResult(dry_run, (), ())

    removed: list[str] = []
    skipped: list[tuple[str, str]] = []
    for entry in sorted(path.iterdir()):
        if entry.is_symlink():
            skipped.append((entry.name, "symlink"))
            continue
        if entry.is_dir():
            skipped.append((entry.name, "directory (not swept)"))
            continue
        if not entry.is_file():
            skipped.append((entry.name, "not a regular file"))
            continue
        if not _is_contained(entry, path):
            skipped.append((entry.name, "resolves outside the temp directory"))
            continue
        try:
            age = now - datetime.fromtimestamp(entry.stat().st_mtime, tz=now.tzinfo)
        except OSError:
            skipped.append((entry.name, "stat failed"))
            continue
        if age < max_age:
            continue
        if not dry_run:
            try:
                entry.unlink(missing_ok=True)
            except OSError:
                skipped.append((entry.name, "delete failed"))
                continue
        removed.append(entry.name)
    return TempSweepResult(dry_run, tuple(removed), tuple(skipped))
