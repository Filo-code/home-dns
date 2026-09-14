"""Compose a StorageReport from real filesystem state. I/O layer over core.storage's pure models."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

from home_dns.core.storage import CategoryUsage, StorageReport, StorageThresholds, classify_usage
from home_dns.storage.artifacts import ArtifactStore
from home_dns.storage.backup import list_backups
from home_dns.storage.disk import DiskUsageProvider, directory_size_bytes
from home_dns.storage.tempfiles import probe_writable


def build_storage_report(
    *,
    root: Path,
    categories: Mapping[str, Path],
    disk: DiskUsageProvider,
    thresholds: StorageThresholds,
    backup_dir: Path,
    artifact_store: ArtifactStore | None,
    artifact_sources: Sequence[str] = (),
    tmp_dir: Path | None = None,
    now: datetime,
) -> StorageReport:
    """``root`` is the filesystem whose usage is classified against ``thresholds`` (typically the
    data_dir's filesystem). ``categories`` maps a reporting name to a directory whose size is
    reported individually (not necessarily on the same filesystem as ``root``)."""
    usage = disk.get(root)
    state = classify_usage(usage, thresholds)

    category_usage = tuple(
        CategoryUsage(
            name=name, path=str(path), bytes=directory_size_bytes(path), exists=path.exists()
        )
        for name, path in categories.items()
    )

    backups = list_backups(backup_dir)
    valid_backups = [b for b in backups if b.valid]
    last_backup_at = valid_backups[0].created_at if valid_backups else None

    artifact_counts: dict[str, int] = {}
    if artifact_store is not None:
        for source_id in artifact_sources:
            state_for_source = artifact_store.state(source_id)
            artifact_counts[source_id] = len(state_for_source.retained())

    return StorageReport(
        checked_at=now,
        disk=usage,
        state=state,
        categories=category_usage,
        last_backup_at=last_backup_at,
        backup_count=len(valid_backups),
        artifact_counts=artifact_counts,
        tmp_dir_usable=probe_writable(tmp_dir) if tmp_dir is not None else True,
    )
