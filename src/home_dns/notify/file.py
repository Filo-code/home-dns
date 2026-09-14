"""Local-file Notifier: appends to an outbox for manual review. No network."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from home_dns.notify.base import Notifier, OutgoingMessage, SendResult


class FileNotifier(Notifier):
    def __init__(self, outbox_path: Path, *, now: Callable[[], datetime] | None = None) -> None:
        self._path = outbox_path
        self._now = now or (lambda: datetime.now(UTC))

    @property
    def name(self) -> str:
        return "file"

    def send(self, message: OutgoingMessage, *, dry_run: bool = True) -> SendResult:
        if dry_run:
            return SendResult(sent=False, detail=f"dry-run: would append to {self._path}")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        record = {"sent_at": self._now().isoformat(), **asdict(message)}
        with open(self._path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return SendResult(sent=True, detail=f"appended to {self._path}")
