"""SQLite connection setup and versioned migrations.

Repositories for concrete entities are added with the first persisted data (A4/A5/A7).
Journal/sync tuning for SD-card wear is decided in ADR 0007 (A4).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

_MIGRATIONS_TABLE = "schema_migrations"


class MigrationError(Exception):
    """Migrations are inconsistent with themselves or with the database."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str


@dataclass(frozen=True)
class MigrationReport:
    dry_run: bool
    current_version: int
    pending: tuple[Migration, ...]
    applied: tuple[Migration, ...]


def open_database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, isolation_level=None)  # explicit transactions below
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def _validate(migrations: Sequence[Migration]) -> None:
    versions = [m.version for m in migrations]
    if versions != list(range(1, len(migrations) + 1)):
        raise MigrationError(f"migration versions must be 1..N without gaps, got {versions}")


def _current_version(connection: sqlite3.Connection) -> int:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (_MIGRATIONS_TABLE,)
    ).fetchone()
    if exists is None:
        return 0
    row = connection.execute(f"SELECT MAX(version) FROM {_MIGRATIONS_TABLE}").fetchone()  # noqa: S608
    return int(row[0] or 0)


def apply_migrations(
    connection: sqlite3.Connection, migrations: Sequence[Migration], *, dry_run: bool = True
) -> MigrationReport:
    _validate(migrations)
    current = _current_version(connection)
    if current > len(migrations):
        raise MigrationError(
            f"database is at version {current}, newer than the {len(migrations)} known migrations"
        )
    pending = tuple(migrations[current:])
    if dry_run:
        return MigrationReport(dry_run=True, current_version=current, pending=pending, applied=())

    applied: list[Migration] = []
    for migration in pending:
        try:
            connection.execute("BEGIN")
            connection.execute(
                f"CREATE TABLE IF NOT EXISTS {_MIGRATIONS_TABLE} ("
                "version INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                "applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            for statement in _split_statements(migration.sql):
                connection.execute(statement)
            connection.execute(
                f"INSERT INTO {_MIGRATIONS_TABLE} (version, name) VALUES (?, ?)",  # noqa: S608
                (migration.version, migration.name),
            )
            connection.execute("COMMIT")
        except sqlite3.Error as exc:
            connection.execute("ROLLBACK")
            raise MigrationError(
                f"migration {migration.version} ({migration.name}) failed: {exc}"
            ) from exc
        applied.append(migration)
    return MigrationReport(
        dry_run=False, current_version=current, pending=pending, applied=tuple(applied)
    )


def _split_statements(sql: str) -> list[str]:
    statements: list[str] = []
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            if buffer.strip():
                statements.append(buffer)
            buffer = ""
    if buffer.strip():
        raise MigrationError(f"incomplete SQL statement: {buffer.strip()!r}")
    return statements
