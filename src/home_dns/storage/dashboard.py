"""Dashboard persistence on ``data_dir/home-dns.db``: users, sessions, devices, rollups.

Schema (docs/specs/a7-backend.md §4-§7). Timestamps are integer UTC epoch seconds.

    users(username PK, role, password_hash, created_at, updated_at)
    sessions(token_digest PK, username FK, csrf_token, created_at, last_seen_at)
    devices(device_id PK, mac UNIQUE, hostname, custom_name, group_id, first_seen, last_seen)
    device_addresses(address PK, device_id FK, last_seen)
    rollups((resolution, bucket_start, device_id) PK, total, blocked, cached, forwarded,
            latency_histogram JSON, blocked_by_source JSON)
    collector_state(id = 1, watermark)
    incident_events(id PK, check_name, transition [opened|recovered], occurred_at, severity)

One connection shared by the API thread pool and the collector thread, serialised by a lock.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from home_dns.core.anomaly import Anomaly, AnomalySeverity
from home_dns.core.auth import Role
from home_dns.core.metrics import Resolution, Rollup
from home_dns.core.monitoring import Severity
from home_dns.storage.sqlite import Migration, apply_migrations, open_database

DATABASE_FILENAME = "home-dns.db"

MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        1,
        "dashboard_initial",
        """
        CREATE TABLE users (
            username TEXT PRIMARY KEY,
            role TEXT NOT NULL CHECK (role IN ('admin', 'viewer')),
            password_hash TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        CREATE TABLE sessions (
            token_digest TEXT PRIMARY KEY,
            username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
            csrf_token TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            last_seen_at INTEGER NOT NULL
        );
        CREATE INDEX sessions_username ON sessions(username);
        CREATE TABLE devices (
            device_id INTEGER PRIMARY KEY,
            mac TEXT UNIQUE,
            hostname TEXT,
            custom_name TEXT,
            group_id TEXT NOT NULL DEFAULT 'DEFAULT',
            first_seen INTEGER NOT NULL,
            last_seen INTEGER NOT NULL
        );
        CREATE TABLE device_addresses (
            address TEXT PRIMARY KEY,
            device_id INTEGER NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
            last_seen INTEGER NOT NULL
        );
        CREATE INDEX device_addresses_device ON device_addresses(device_id);
        CREATE TABLE rollups (
            resolution TEXT NOT NULL CHECK (resolution IN ('minute', 'hour', 'day')),
            bucket_start INTEGER NOT NULL,
            device_id INTEGER NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
            total INTEGER NOT NULL,
            blocked INTEGER NOT NULL,
            cached INTEGER NOT NULL,
            forwarded INTEGER NOT NULL,
            latency_histogram TEXT NOT NULL,
            blocked_by_source TEXT NOT NULL,
            PRIMARY KEY (resolution, bucket_start, device_id)
        ) WITHOUT ROWID;
        CREATE INDEX rollups_device ON rollups(device_id, resolution, bucket_start);
        CREATE TABLE collector_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            watermark INTEGER NOT NULL
        );
        """,
    ),
    Migration(
        2,
        "incident_events",
        """
        CREATE TABLE incident_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            check_name TEXT NOT NULL,
            transition TEXT NOT NULL CHECK (transition IN ('opened', 'recovered')),
            occurred_at INTEGER NOT NULL,
            severity TEXT CHECK (severity IN ('critical', 'warning', 'info'))
        );
        CREATE INDEX incident_events_check_time ON incident_events(check_name, occurred_at);
        """,
    ),
    Migration(
        3,
        "anomalies",
        """
        CREATE TABLE anomalies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
            detected_at INTEGER NOT NULL,
            severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high')),
            score INTEGER NOT NULL,
            signals TEXT NOT NULL,
            reason TEXT NOT NULL
        );
        CREATE INDEX anomalies_device_time ON anomalies(device_id, detected_at);
        CREATE INDEX anomalies_time ON anomalies(detected_at);
        """,
    ),
)


def _epoch(moment: datetime) -> int:
    return int(moment.timestamp())


def _dt(epoch: int) -> datetime:
    return datetime.fromtimestamp(epoch, UTC)


@dataclass(frozen=True)
class UserRecord:
    username: str
    role: Role
    password_hash: str


@dataclass(frozen=True)
class SessionRecord:
    token_digest: str
    username: str
    role: Role
    csrf_token: str
    created_at: datetime
    last_seen_at: datetime


@dataclass(frozen=True)
class DeviceRecord:
    device_id: int
    mac: str | None
    hostname: str | None
    custom_name: str | None
    group_id: str
    first_seen: datetime
    last_seen: datetime
    addresses: tuple[str, ...] = ()


@dataclass(frozen=True)
class DeviceUpsert:
    """Collector-owned fields only; custom_name and group_id are never overwritten."""

    device_id: int
    mac: str | None
    hostname: str | None
    first_seen: datetime
    last_seen: datetime


@dataclass(frozen=True)
class IncidentEventRecord:
    """One persisted opened/recovered transition. See the ``incident_events`` migration doc for
    why there is no "notified" field."""

    check_name: str
    transition: str
    occurred_at: datetime
    severity: Severity | None


@dataclass(frozen=True)
class AnomalyRecord:
    """One persisted, already-evaluated anomaly event — never a raw query. See
    core/anomaly.py's ``Anomaly`` for the pure model this is the storage twin of."""

    id: int
    device_id: int
    detected_at: datetime
    severity: AnomalySeverity
    score: int
    signals: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class FlushBatch:
    watermark: datetime
    devices: tuple[DeviceUpsert, ...] = ()
    addresses: tuple[tuple[str, int, datetime], ...] = ()  # (address, device_id, last_seen)
    rollups: tuple[tuple[Resolution, datetime, int, Rollup], ...] = ()
    retention_cutoffs: dict[Resolution, datetime] = field(default_factory=dict)
    anomalies: tuple[Anomaly, ...] = ()
    anomaly_retention_cutoff: datetime | None = None


class DashboardStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._lock = threading.Lock()

    @classmethod
    def open(cls, data_dir: Path) -> DashboardStore:
        """Open (creating if needed) and migrate the application database."""
        data_dir.mkdir(parents=True, exist_ok=True)
        connection = open_database(data_dir / DATABASE_FILENAME, check_same_thread=False)
        apply_migrations(connection, MIGRATIONS, dry_run=False)
        return cls(connection)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield self._connection
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
            self._connection.execute("COMMIT")

    def _read(self, sql: str, params: Iterable[object] = ()) -> list[sqlite3.Row]:
        with self._lock:
            cursor = self._connection.execute(sql, tuple(params))
            cursor.row_factory = sqlite3.Row
            return cursor.fetchall()

    # ------------------------------------------------------------------------------ users

    def set_user(self, username: str, role: Role, password_hash: str, *, now: datetime) -> None:
        """Create or replace a user. Existing sessions of that user are revoked."""
        with self._transaction() as conn:
            conn.execute(
                "INSERT INTO users (username, role, password_hash, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(username) DO UPDATE SET "
                "role = excluded.role, password_hash = excluded.password_hash, "
                "updated_at = excluded.updated_at",
                (username, role.value, password_hash, _epoch(now), _epoch(now)),
            )
            conn.execute("DELETE FROM sessions WHERE username = ?", (username,))

    def get_user(self, username: str) -> UserRecord | None:
        rows = self._read(
            "SELECT username, role, password_hash FROM users WHERE username = ?", (username,)
        )
        if not rows:
            return None
        return UserRecord(rows[0]["username"], Role(rows[0]["role"]), rows[0]["password_hash"])

    def list_users(self) -> list[tuple[str, Role]]:
        rows = self._read("SELECT username, role FROM users ORDER BY username")
        return [(row["username"], Role(row["role"])) for row in rows]

    # --------------------------------------------------------------------------- sessions

    def create_session(
        self, token_digest: str, username: str, csrf_token: str, *, now: datetime
    ) -> None:
        with self._transaction() as conn:
            conn.execute(
                "INSERT INTO sessions (token_digest, username, csrf_token, created_at, "
                "last_seen_at) VALUES (?, ?, ?, ?, ?)",
                (token_digest, username, csrf_token, _epoch(now), _epoch(now)),
            )

    def get_session(self, token_digest: str) -> SessionRecord | None:
        rows = self._read(
            "SELECT s.token_digest, s.username, u.role, s.csrf_token, s.created_at, "
            "s.last_seen_at FROM sessions s JOIN users u USING (username) "
            "WHERE s.token_digest = ?",
            (token_digest,),
        )
        if not rows:
            return None
        row = rows[0]
        return SessionRecord(
            row["token_digest"],
            row["username"],
            Role(row["role"]),
            row["csrf_token"],
            _dt(row["created_at"]),
            _dt(row["last_seen_at"]),
        )

    def touch_session(self, token_digest: str, *, now: datetime) -> None:
        with self._transaction() as conn:
            conn.execute(
                "UPDATE sessions SET last_seen_at = ? WHERE token_digest = ?",
                (_epoch(now), token_digest),
            )

    def delete_session(self, token_digest: str) -> None:
        with self._transaction() as conn:
            conn.execute("DELETE FROM sessions WHERE token_digest = ?", (token_digest,))

    def delete_expired_sessions(self, *, idle_before: datetime, created_before: datetime) -> int:
        with self._transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE last_seen_at < ? OR created_at < ?",
                (_epoch(idle_before), _epoch(created_before)),
            )
            return cursor.rowcount

    # ---------------------------------------------------------------------------- devices

    def list_devices(self) -> list[DeviceRecord]:
        return self._devices("")

    def get_device(self, device_id: int) -> DeviceRecord | None:
        found = self._devices("WHERE d.device_id = ?", (device_id,))
        return found[0] if found else None

    def _devices(self, where: str, params: Iterable[object] = ()) -> list[DeviceRecord]:
        rows = self._read(
            "SELECT d.*, group_concat(a.address, ' ') AS addresses FROM devices d "  # noqa: S608
            "LEFT JOIN device_addresses a ON a.device_id = d.device_id "
            # only addresses seen within a day of the device itself: rotating IPv6 accumulates
            f"AND a.last_seen >= d.last_seen - 86400 {where} "
            "GROUP BY d.device_id ORDER BY d.device_id",
            params,
        )
        return [
            DeviceRecord(
                device_id=row["device_id"],
                mac=row["mac"],
                hostname=row["hostname"],
                custom_name=row["custom_name"],
                group_id=row["group_id"],
                first_seen=_dt(row["first_seen"]),
                last_seen=_dt(row["last_seen"]),
                addresses=tuple(sorted((row["addresses"] or "").split())),
            )
            for row in rows
        ]

    def rename_device(self, device_id: int, custom_name: str | None) -> bool:
        with self._transaction() as conn:
            cursor = conn.execute(
                "UPDATE devices SET custom_name = ? WHERE device_id = ?", (custom_name, device_id)
            )
            return cursor.rowcount == 1

    def assign_group(self, device_id: int, group_id: str) -> bool:
        with self._transaction() as conn:
            cursor = conn.execute(
                "UPDATE devices SET group_id = ? WHERE device_id = ?", (group_id, device_id)
            )
            return cursor.rowcount == 1

    def address_bindings(self) -> dict[str, int]:
        rows = self._read("SELECT address, device_id FROM device_addresses")
        return {row["address"]: row["device_id"] for row in rows}

    # ---------------------------------------------------------------------------- metrics

    def load_watermark(self) -> datetime | None:
        rows = self._read("SELECT watermark FROM collector_state WHERE id = 1")
        return _dt(rows[0]["watermark"]) if rows else None

    def flush(self, batch: FlushBatch) -> None:
        """Everything in one transaction, watermark included: all or nothing."""
        with self._transaction() as conn:
            for device in batch.devices:
                conn.execute(
                    "INSERT INTO devices (device_id, mac, hostname, first_seen, last_seen) "
                    "VALUES (?, ?, ?, ?, ?) ON CONFLICT(device_id) DO UPDATE SET "
                    "mac = COALESCE(excluded.mac, mac), "
                    "hostname = COALESCE(excluded.hostname, hostname), "
                    "first_seen = MIN(first_seen, excluded.first_seen), "
                    "last_seen = MAX(last_seen, excluded.last_seen)",
                    (
                        device.device_id,
                        device.mac,
                        device.hostname,
                        _epoch(device.first_seen),
                        _epoch(device.last_seen),
                    ),
                )
            for address, device_id, last_seen in batch.addresses:
                conn.execute(
                    "INSERT INTO device_addresses (address, device_id, last_seen) VALUES (?, ?, ?) "
                    "ON CONFLICT(address) DO UPDATE SET device_id = excluded.device_id, "
                    "last_seen = MAX(last_seen, excluded.last_seen)",
                    (address, device_id, _epoch(last_seen)),
                )
            for resolution, start, device_id, rollup in batch.rollups:
                _merge_rollup(conn, resolution, _epoch(start), device_id, rollup)
            for resolution, cutoff in batch.retention_cutoffs.items():
                conn.execute(
                    "DELETE FROM rollups WHERE resolution = ? AND bucket_start < ?",
                    (resolution.value, _epoch(cutoff)),
                )
            if Resolution.DAY in batch.retention_cutoffs:
                conn.execute(
                    "DELETE FROM device_addresses WHERE last_seen < ?",
                    (_epoch(batch.retention_cutoffs[Resolution.DAY]),),
                )
            for anomaly in batch.anomalies:
                conn.execute(
                    "INSERT INTO anomalies (device_id, detected_at, severity, score, signals, "
                    "reason) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        anomaly.device_id,
                        _epoch(anomaly.detected_at),
                        anomaly.severity,
                        anomaly.score,
                        json.dumps([s.value for s in anomaly.signals]),
                        anomaly.reason,
                    ),
                )
            if batch.anomaly_retention_cutoff is not None:
                conn.execute(
                    "DELETE FROM anomalies WHERE detected_at < ?",
                    (_epoch(batch.anomaly_retention_cutoff),),
                )
            conn.execute(
                "INSERT INTO collector_state (id, watermark) VALUES (1, ?) "
                "ON CONFLICT(id) DO UPDATE SET watermark = excluded.watermark",
                (_epoch(batch.watermark),),
            )

    def rollups(
        self,
        resolution: Resolution,
        since: datetime,
        until: datetime,
        *,
        device_id: int | None = None,
    ) -> list[tuple[datetime, int, Rollup]]:
        """Rows with ``since <= bucket_start < until``, ordered by bucket then device."""
        sql = (
            "SELECT * FROM rollups WHERE resolution = ? AND bucket_start >= ? AND bucket_start < ?"
        )
        params: list[object] = [resolution.value, _epoch(since), _epoch(until)]
        if device_id is not None:
            sql += " AND device_id = ?"
            params.append(device_id)
        rows = self._read(sql + " ORDER BY bucket_start, device_id", params)
        return [(_dt(row["bucket_start"]), row["device_id"], _rollup(row)) for row in rows]

    # --------------------------------------------------------------------- incident history

    def record_incident_event(
        self,
        check_name: str,
        transition: str,
        *,
        occurred_at: datetime,
        severity: Severity | None,
    ) -> None:
        with self._transaction() as conn:
            conn.execute(
                "INSERT INTO incident_events (check_name, transition, occurred_at, severity) "
                "VALUES (?, ?, ?, ?)",
                (check_name, transition, _epoch(occurred_at), severity),
            )

    def list_incident_events(
        self,
        *,
        since: datetime | None = None,
        check_name: str | None = None,
        limit: int = 100,
    ) -> list[IncidentEventRecord]:
        """Most recent first."""
        sql = "SELECT * FROM incident_events WHERE 1 = 1"
        params: list[object] = []
        if since is not None:
            sql += " AND occurred_at >= ?"
            params.append(_epoch(since))
        if check_name is not None:
            sql += " AND check_name = ?"
            params.append(check_name)
        rows = self._read(sql + " ORDER BY occurred_at DESC, id DESC LIMIT ?", (*params, limit))
        return [
            IncidentEventRecord(
                check_name=row["check_name"],
                transition=row["transition"],
                occurred_at=_dt(row["occurred_at"]),
                severity=row["severity"],
            )
            for row in rows
        ]

    # ----------------------------------------------------------------------------- anomalies

    def list_anomalies(
        self,
        *,
        since: datetime | None = None,
        device_id: int | None = None,
        limit: int = 100,
    ) -> list[AnomalyRecord]:
        """Most recent first. Security/anomaly events, kept deliberately separate from
        ``incident_events`` (infrastructure health) — see core/anomaly.py's module docstring."""
        sql = "SELECT * FROM anomalies WHERE 1 = 1"
        params: list[object] = []
        if since is not None:
            sql += " AND detected_at >= ?"
            params.append(_epoch(since))
        if device_id is not None:
            sql += " AND device_id = ?"
            params.append(device_id)
        rows = self._read(sql + " ORDER BY detected_at DESC, id DESC LIMIT ?", (*params, limit))
        return [_anomaly_record(row) for row in rows]

    def get_anomaly(self, anomaly_id: int) -> AnomalyRecord | None:
        rows = self._read("SELECT * FROM anomalies WHERE id = ?", (anomaly_id,))
        return _anomaly_record(rows[0]) if rows else None


def _anomaly_record(row: sqlite3.Row) -> AnomalyRecord:
    return AnomalyRecord(
        id=row["id"],
        device_id=row["device_id"],
        detected_at=_dt(row["detected_at"]),
        severity=row["severity"],
        score=row["score"],
        signals=tuple(json.loads(row["signals"])),
        reason=row["reason"],
    )


def _rollup(row: sqlite3.Row) -> Rollup:
    return Rollup(
        total=row["total"],
        blocked=row["blocked"],
        cached=row["cached"],
        forwarded=row["forwarded"],
        latency_histogram=json.loads(row["latency_histogram"]),
        blocked_by_source=json.loads(row["blocked_by_source"]),
    )


def _merge_rollup(
    conn: sqlite3.Connection, resolution: Resolution, start: int, device_id: int, delta: Rollup
) -> None:
    cursor = conn.execute(
        "SELECT * FROM rollups WHERE resolution = ? AND bucket_start = ? AND device_id = ?",
        (resolution.value, start, device_id),
    )
    cursor.row_factory = sqlite3.Row
    existing = cursor.fetchone()
    merged = _rollup(existing) if existing else Rollup()
    merged.merge(delta)
    conn.execute(
        "INSERT OR REPLACE INTO rollups (resolution, bucket_start, device_id, total, blocked, "
        "cached, forwarded, latency_histogram, blocked_by_source) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            resolution.value,
            start,
            device_id,
            merged.total,
            merged.blocked,
            merged.cached,
            merged.forwarded,
            json.dumps(merged.latency_histogram),
            json.dumps(merged.blocked_by_source, sort_keys=True),
        ),
    )
