"""Verified, versioned backups of named source directories.

Layout:

    <root>/backup-<UTC compact timestamp>/manifest.json
    <root>/backup-<UTC compact timestamp>/<source-name>/...   (file copies, structure preserved)

Safety rules, mirroring storage/artifacts.py:
- A backup is written to a temp directory and published with one atomic ``os.replace`` of the
  whole directory; ``manifest.json`` is written last, so an interrupted backup can never look
  complete.
- Every file's SHA-256 is recorded at creation and re-verified on read; a backup that fails
  verification is reported, never silently trusted or silently deleted.
- Only directories matching this module's own ``backup-<timestamp>`` naming are ever pruned.
- The single newest *valid* backup is never pruned, regardless of the configured retention count.
- Every mutating function defaults to dry_run=True.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_NAME_RE = re.compile(r"backup-(?P<stamp>\d{8}T\d{6}Z)")
_STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
_SOURCE_NAME_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")


class BackupError(Exception):
    """A backup operation failed, or a backup is missing/corrupted."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _format_stamp(now: datetime) -> str:
    return now.astimezone(UTC).strftime(_STAMP_FORMAT)


def _parse_stamp(stamp: str) -> datetime:
    return datetime.strptime(stamp, _STAMP_FORMAT).replace(tzinfo=UTC)


@dataclass(frozen=True)
class ManifestEntry:
    source: str
    relative_path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class BackupManifest:
    created_at: datetime
    entries: tuple[ManifestEntry, ...]

    @property
    def total_bytes(self) -> int:
        return sum(e.size_bytes for e in self.entries)

    def to_json(self) -> str:
        payload = {
            "created_at": self.created_at.isoformat(),
            "entries": [
                {
                    "source": e.source,
                    "path": e.relative_path,
                    "sha256": e.sha256,
                    "size": e.size_bytes,
                }
                for e in self.entries
            ],
        }
        return json.dumps(payload, indent=2, sort_keys=True)

    @staticmethod
    def from_json(text: str) -> BackupManifest:
        data = json.loads(text)
        entries = tuple(
            ManifestEntry(e["source"], e["path"], e["sha256"], e["size"]) for e in data["entries"]
        )
        return BackupManifest(datetime.fromisoformat(data["created_at"]), entries)


@dataclass(frozen=True)
class BackupInfo:
    name: str
    created_at: datetime
    path: Path
    valid: bool
    error: str | None = None


@dataclass(frozen=True)
class BackupResult:
    dry_run: bool
    name: str
    manifest: BackupManifest
    path: Path


@dataclass(frozen=True)
class VerifyMismatch:
    relative_path: str
    reason: str  # "missing" or "checksum mismatch"


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    checked: int
    mismatches: tuple[VerifyMismatch, ...]


@dataclass(frozen=True)
class RestoreResult:
    dry_run: bool
    restored: tuple[str, ...]  # "<source>/<relative_path>"


@dataclass(frozen=True)
class PruneResult:
    dry_run: bool
    kept: tuple[str, ...]
    removed: tuple[str, ...]


def _iter_source_files(source_path: Path) -> list[Path]:
    if source_path.is_file():
        return [source_path]
    if not source_path.is_dir():
        return []
    return sorted(p for p in source_path.rglob("*") if p.is_file() and not p.is_symlink())


def create_backup(
    sources: Mapping[str, Path], destination_dir: Path, *, now: datetime, dry_run: bool = True
) -> BackupResult:
    """Copy every file under each named source into one new, atomically-published backup."""
    for name in sources:
        if not _SOURCE_NAME_RE.fullmatch(name):
            raise BackupError(f"invalid source name {name!r}")

    stamp = _format_stamp(now)
    name = f"backup-{stamp}"
    final_dir = destination_dir / name
    entries: list[ManifestEntry] = []
    for source_name, source_path in sources.items():
        base = source_path if source_path.is_dir() else source_path.parent
        for file_path in _iter_source_files(source_path):
            relative = (
                file_path.relative_to(base).as_posix() if source_path.is_dir() else file_path.name
            )
            entries.append(
                ManifestEntry(
                    source_name, relative, _sha256_file(file_path), file_path.stat().st_size
                )
            )
    manifest = BackupManifest(now, tuple(entries))

    if not dry_run:
        tmp_dir = destination_dir / f".{name}.tmp"
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        tmp_dir.mkdir(parents=True)
        try:
            for source_name, source_path in sources.items():
                base = source_path if source_path.is_dir() else source_path.parent
                for file_path in _iter_source_files(source_path):
                    relative_path = (
                        file_path.relative_to(base)
                        if source_path.is_dir()
                        else Path(file_path.name)
                    )
                    target = tmp_dir / source_name / relative_path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file_path, target)
            (tmp_dir / "manifest.json").write_text(manifest.to_json(), encoding="utf-8")
            if final_dir.exists():
                raise BackupError(f"backup {name!r} already exists")
            os.replace(tmp_dir, final_dir)
        except Exception:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise

    return BackupResult(dry_run, name, manifest, final_dir)


def list_backups(destination_dir: Path) -> list[BackupInfo]:
    """Newest first. Directories that don't match the naming pattern are ignored entirely
    (never listed, never candidates for pruning). A match with no/invalid manifest is listed
    as invalid, never silently dropped."""
    if not destination_dir.is_dir():
        return []
    infos: list[BackupInfo] = []
    for entry in destination_dir.iterdir():
        if not entry.is_dir():
            continue
        match = _NAME_RE.fullmatch(entry.name)
        if not match:
            continue
        try:
            created_at = _parse_stamp(match.group("stamp"))
        except ValueError:
            infos.append(
                BackupInfo(
                    entry.name,
                    datetime.min.replace(tzinfo=UTC),
                    entry,
                    False,
                    "unparseable timestamp",
                )
            )
            continue
        manifest_path = entry / "manifest.json"
        if not manifest_path.is_file():
            infos.append(BackupInfo(entry.name, created_at, entry, False, "missing manifest.json"))
            continue
        try:
            BackupManifest.from_json(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            infos.append(
                BackupInfo(entry.name, created_at, entry, False, f"corrupted manifest: {exc}")
            )
            continue
        infos.append(BackupInfo(entry.name, created_at, entry, True))
    return sorted(infos, key=lambda i: i.created_at, reverse=True)


def verify_backup(backup_dir: Path) -> VerifyResult:
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.is_file():
        raise BackupError(f"{backup_dir}: missing manifest.json")
    manifest = BackupManifest.from_json(manifest_path.read_text(encoding="utf-8"))
    mismatches: list[VerifyMismatch] = []
    for e in manifest.entries:
        file_path = backup_dir / e.source / e.relative_path
        if not file_path.is_file():
            mismatches.append(VerifyMismatch(f"{e.source}/{e.relative_path}", "missing"))
            continue
        if _sha256_file(file_path) != e.sha256:
            mismatches.append(VerifyMismatch(f"{e.source}/{e.relative_path}", "checksum mismatch"))
    return VerifyResult(
        ok=not mismatches, checked=len(manifest.entries), mismatches=tuple(mismatches)
    )


def restore_backup(
    backup_dir: Path, targets: Mapping[str, Path], *, dry_run: bool = True
) -> RestoreResult:
    """Verify first; refuse to restore anything if verification fails."""
    verification = verify_backup(backup_dir)
    if not verification.ok:
        raise BackupError(
            f"{backup_dir}: verification failed ({len(verification.mismatches)} mismatch(es)); "
            "restore refused"
        )
    manifest = BackupManifest.from_json((backup_dir / "manifest.json").read_text(encoding="utf-8"))
    restored: list[str] = []
    for e in manifest.entries:
        if e.source not in targets:
            continue
        source_file = backup_dir / e.source / e.relative_path
        target_file = targets[e.source] / e.relative_path
        if not dry_run:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = target_file.with_name(f".{target_file.name}.restoring.tmp")
            shutil.copy2(source_file, tmp)
            os.replace(tmp, target_file)
        restored.append(f"{e.source}/{e.relative_path}")
    return RestoreResult(dry_run, tuple(restored))


def prune_backups(destination_dir: Path, *, keep: int, dry_run: bool = True) -> PruneResult:
    """Keep the newest ``keep`` *valid* backups (minimum effective 1: the newest valid backup is
    never removable). Invalid backups beyond the newest valid one are pruned too, since they are
    unusable; an invalid backup that is also the newest entry is kept and reported, not deleted,
    so an operator can inspect why it failed instead of losing the only recent copy."""
    infos = list_backups(destination_dir)
    if not infos:
        return PruneResult(dry_run, (), ())
    effective_keep = max(keep, 1)
    valid = [i for i in infos if i.valid]
    keep_names = {i.name for i in valid[:effective_keep]}
    if not valid:
        keep_names = {infos[0].name}  # nothing valid: keep the newest entry, for inspection

    to_remove = [i for i in infos if i.name not in keep_names]
    if not dry_run:
        for info in to_remove:
            shutil.rmtree(info.path, ignore_errors=True)
    return PruneResult(
        dry_run,
        tuple(sorted(keep_names)),
        tuple(sorted(i.name for i in to_remove)),
    )
