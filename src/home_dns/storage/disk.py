"""Filesystem usage reads. Uses filesystem statistics, never estimates from application files."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol

from home_dns.core.storage import DiskUsage


class DiskUsageProvider(Protocol):
    def get(self, path: Path) -> DiskUsage: ...


class SystemDiskUsage:
    """Reads the real filesystem containing ``path`` via the OS (statvfs under the hood).

    ``path`` need not exist yet (e.g. data_dir before it has ever been written to): disk usage is
    a property of the filesystem, so the nearest existing ancestor is used instead.
    """

    def get(self, path: Path) -> DiskUsage:
        target = path
        while not target.exists():
            parent = target.parent
            if parent == target:
                break  # reached the filesystem root without finding an existing directory
            target = parent
        total, used, free = shutil.disk_usage(target)
        return DiskUsage(total_bytes=total, used_bytes=used, free_bytes=free)


def directory_size_bytes(path: Path) -> int:
    """Sum of file sizes under ``path`` (recursive). 0 if ``path`` does not exist. Symlinks are
    not followed (their target's size is not double-counted from elsewhere in the tree)."""
    if not path.exists():
        return 0
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file() and not entry.is_symlink():
            try:
                total += entry.stat().st_size
            except OSError:
                continue
    return total
