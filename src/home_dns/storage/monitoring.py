"""Durable state for A5 monitoring: incidents and blocklist-freshness counters.

Layout (under ``data_dir``, never ``tmp_dir`` — this state must survive a reboot, since each
scheduled check is a fresh process invocation and "N consecutive runs" would otherwise reset
spuriously):

    <root>/incidents/<check_name>.json
    <root>/blocklist-freshness/<source_id>.json

Same atomic-write discipline as ``storage/artifacts.py``: temp file + fsync + ``os.replace``.
Every mutating method defaults to ``dry_run=True``.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from home_dns.core.monitoring import FreshnessCounter, Incident, IncidentState

_NAME_RE = re.compile(r"[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*")


class MonitoringStoreError(Exception):
    """The monitoring state directory contains something invalid or unreadable."""


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    with open(tmp, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _safe_path(root: Path, name: str) -> Path:
    if not _NAME_RE.fullmatch(name):
        raise MonitoringStoreError(f"invalid name {name!r}")
    return root / f"{name}.json"


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class MonitoringStore:
    def __init__(self, root: Path) -> None:
        self._incidents_dir = root / "incidents"
        self._freshness_dir = root / "blocklist-freshness"

    def load_incident(self, check_name: str) -> Incident:
        path = _safe_path(self._incidents_dir, check_name)
        if not path.is_file():
            return Incident(check_name=check_name)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Incident(
                check_name=check_name,
                state=IncidentState(data["state"]),
                consecutive_problem=data["consecutive_problem"],
                consecutive_ok=data["consecutive_ok"],
                opened_at=_parse_dt(data.get("opened_at")),
                last_change_at=_parse_dt(data.get("last_change_at")),
                last_notified_at=_parse_dt(data.get("last_notified_at")),
            )
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            raise MonitoringStoreError(f"{path}: corrupted incident state") from exc

    def list_incidents(self) -> list[Incident]:
        """Every stored incident, by check name. Files with invalid names are ignored."""
        if not self._incidents_dir.is_dir():
            return []
        return [
            self.load_incident(path.stem)
            for path in sorted(self._incidents_dir.glob("*.json"))
            if _NAME_RE.fullmatch(path.stem)
        ]

    def save_incident(self, incident: Incident, *, dry_run: bool = True) -> None:
        if dry_run:
            return
        payload = {
            "state": incident.state.value,
            "consecutive_problem": incident.consecutive_problem,
            "consecutive_ok": incident.consecutive_ok,
            "opened_at": incident.opened_at.isoformat() if incident.opened_at else None,
            "last_change_at": incident.last_change_at.isoformat()
            if incident.last_change_at
            else None,
            "last_notified_at": incident.last_notified_at.isoformat()
            if incident.last_notified_at
            else None,
        }
        _atomic_write(
            _safe_path(self._incidents_dir, incident.check_name),
            json.dumps(payload, indent=2).encode("utf-8"),
        )

    def load_freshness(self, source_id: str) -> FreshnessCounter:
        path = _safe_path(self._freshness_dir, source_id)
        if not path.is_file():
            return FreshnessCounter(source_id=source_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return FreshnessCounter(
                source_id=source_id,
                consecutive_kept_previous=data["consecutive_kept_previous"],
            )
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            raise MonitoringStoreError(f"{path}: corrupted freshness state") from exc

    def save_freshness(self, counter: FreshnessCounter, *, dry_run: bool = True) -> None:
        if dry_run:
            return
        _atomic_write(
            _safe_path(self._freshness_dir, counter.source_id),
            json.dumps(asdict(counter), indent=2).encode("utf-8"),
        )


__all__ = ["MonitoringStore", "MonitoringStoreError"]
