"""Durable state for A6 anti-spam: last-sent time per key and the trailing-hour send window.

Layout (under ``data_dir``, never ``tmp_dir`` — must survive a reboot, matching A5's monitoring
state): ``<root>/anti_spam.json``. Same atomic-write discipline as ``storage/monitoring.py``.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from home_dns.core.notify import AntiSpamState


class NotifyStoreError(Exception):
    """The anti-spam state file is invalid or unreadable."""


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    with open(tmp, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


class NotifyStore:
    def __init__(self, root: Path) -> None:
        self._path = root / "anti_spam.json"

    def load(self) -> AntiSpamState:
        if not self._path.is_file():
            return AntiSpamState()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return AntiSpamState(
                last_sent_at={
                    k: datetime.fromisoformat(v) for k, v in data["last_sent_at"].items()
                },
                sent_within_hour=tuple(
                    datetime.fromisoformat(v) for v in data["sent_within_hour"]
                ),
            )
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            raise NotifyStoreError(f"{self._path}: corrupted anti-spam state") from exc

    def save(self, state: AntiSpamState, *, dry_run: bool = True) -> None:
        if dry_run:
            return
        payload = {
            "last_sent_at": {k: v.isoformat() for k, v in state.last_sent_at.items()},
            "sent_within_hour": [v.isoformat() for v in state.sent_within_hour],
        }
        _atomic_write(self._path, json.dumps(payload, indent=2).encode("utf-8"))


__all__ = ["NotifyStore", "NotifyStoreError"]
