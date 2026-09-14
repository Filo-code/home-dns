"""Bounded application logging.

Size- and count-bounded rotation (not day-based): a single very chatty period cannot overflow
storage regardless of write volume, because the cap is on bytes x file count, not on elapsed time.
See docs/specs/a4-storage-maintenance.md §8 for the full reasoning, including why journald's own
retention (C-stage, out of scope here) is the right place to bound systemd-service logs.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from home_dns.storage.disk import directory_size_bytes


def build_rotating_file_handler(
    path: Path, *, max_bytes: int, backup_count: int
) -> logging.handlers.RotatingFileHandler:
    """A RotatingFileHandler writing to ``path``, capped at ``max_bytes`` x (backup_count + 1)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s"))
    return handler


def log_directory_usage_bytes(log_dir: Path) -> int:
    return directory_size_bytes(log_dir)
