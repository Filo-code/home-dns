import sqlite3
from pathlib import Path

import pytest

from home_dns.storage.sqlite import (
    Migration,
    MigrationError,
    apply_migrations,
    backup_database,
    check_integrity,
    checkpoint_wal,
    open_database,
    vacuum,
)

MIGRATIONS = (
    Migration(1, "create_items", "CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT);"),
    Migration(2, "add_index", "CREATE INDEX idx_items_name ON items(name);\nSELECT 1;"),
)


def _tables(db_path: Path) -> set[str]:
    with open_database(db_path) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','index')")
        return {row[0] for row in rows}


def test_open_database_sets_pragmas(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "a.db")
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()


def test_dry_run_is_the_default_and_changes_nothing(tmp_path: Path) -> None:
    db = tmp_path / "a.db"
    conn = open_database(db)
    report = apply_migrations(conn, MIGRATIONS)
    conn.close()
    assert report.dry_run is True
    assert [m.version for m in report.pending] == [1, 2]
    assert report.applied == ()
    assert _tables(db) == set()


def test_apply_then_rerun_is_a_no_op(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "a.db")
    first = apply_migrations(conn, MIGRATIONS, dry_run=False)
    second = apply_migrations(conn, MIGRATIONS, dry_run=False)
    assert [m.version for m in first.applied] == [1, 2]
    assert second.current_version == 2 and second.applied == ()
    conn.close()
    assert {"items", "idx_items_name", "schema_migrations"} <= _tables(tmp_path / "a.db")


def test_incremental_migration(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "a.db")
    apply_migrations(conn, MIGRATIONS[:1], dry_run=False)
    report = apply_migrations(conn, MIGRATIONS, dry_run=False)
    assert report.current_version == 1
    assert [m.version for m in report.applied] == [2]
    conn.close()


@pytest.mark.parametrize(
    "migrations",
    [
        (Migration(2, "x", "SELECT 1;"),),
        (Migration(1, "a", "SELECT 1;"), Migration(1, "b", "SELECT 1;")),
        (Migration(1, "a", "SELECT 1;"), Migration(3, "c", "SELECT 1;")),
    ],
)
def test_inconsistent_versions_are_rejected(
    tmp_path: Path, migrations: tuple[Migration, ...]
) -> None:
    with open_database(tmp_path / "a.db") as conn, pytest.raises(MigrationError, match=r"1\.\.N"):
        apply_migrations(conn, migrations)


def test_failing_migration_rolls_back_and_is_not_recorded(tmp_path: Path) -> None:
    broken = (MIGRATIONS[0], Migration(2, "broken", "CREATE TABLE ok_table (id INT);\nNOT SQL;"))
    conn = open_database(tmp_path / "a.db")
    with pytest.raises(MigrationError, match="migration 2"):
        apply_migrations(conn, broken, dry_run=False)
    assert apply_migrations(conn, broken).current_version == 1
    conn.close()
    assert "ok_table" not in _tables(tmp_path / "a.db")


def test_incomplete_statement_is_rejected(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "a.db")
    with pytest.raises(MigrationError, match="incomplete SQL"):
        apply_migrations(conn, (Migration(1, "x", "CREATE TABLE t (id INT)"),), dry_run=False)
    conn.close()


def test_database_newer_than_code_is_rejected(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "a.db")
    apply_migrations(conn, MIGRATIONS, dry_run=False)
    with pytest.raises(MigrationError, match="newer than"):
        apply_migrations(conn, MIGRATIONS[:1])
    conn.close()


# ---------------------------------------------------------------------- A4: backup / integrity


def test_backup_database_dry_run_writes_nothing(tmp_path: Path) -> None:
    source = open_database(tmp_path / "source.db")
    apply_migrations(source, MIGRATIONS, dry_run=False)
    source.execute("INSERT INTO items (name) VALUES ('a')")
    destination = tmp_path / "copy.db"
    result = backup_database(source, destination, dry_run=True)
    assert result.dry_run and result.page_count > 0
    assert not destination.exists()
    source.close()


def test_backup_database_apply_produces_an_independent_readable_copy(tmp_path: Path) -> None:
    source = open_database(tmp_path / "source.db")
    apply_migrations(source, MIGRATIONS, dry_run=False)
    source.execute("INSERT INTO items (name) VALUES ('hello')")
    destination = tmp_path / "copy.db"
    result = backup_database(source, destination, dry_run=False)
    assert not result.dry_run and destination.is_file()
    source.execute("INSERT INTO items (name) VALUES ('after-backup')")

    copy = open_database(destination)
    rows = copy.execute("SELECT name FROM items").fetchall()
    copy.close()
    assert rows == [("hello",)]  # the copy is a point-in-time snapshot, unaffected by later writes
    source.close()


def test_backup_database_leaves_no_temp_file_on_success(tmp_path: Path) -> None:
    source = open_database(tmp_path / "source.db")
    apply_migrations(source, MIGRATIONS, dry_run=False)
    destination = tmp_path / "copy.db"
    backup_database(source, destination, dry_run=False)
    assert list(tmp_path.glob("*.tmp")) == []
    source.close()


def test_check_integrity_ok_on_healthy_database(tmp_path: Path) -> None:
    connection = open_database(tmp_path / "a.db")
    apply_migrations(connection, MIGRATIONS, dry_run=False)
    quick = check_integrity(connection)
    thorough = check_integrity(connection, quick=False)
    assert quick.ok and quick.messages == ("ok",)
    assert thorough.ok
    connection.close()


def test_check_integrity_detects_corruption(tmp_path: Path) -> None:
    path = tmp_path / "a.db"
    connection = open_database(path)
    apply_migrations(connection, MIGRATIONS, dry_run=False)
    for i in range(200):
        connection.execute("INSERT INTO items (name) VALUES (?)", (f"row-{i}",))
    connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    connection.close()

    # Truncating mid-file reliably breaks a multi-page database, unlike flipping bytes that may
    # land in unused space. This corrupts the file so a fresh connection can detect it.
    size = path.stat().st_size
    assert size > 4096, "test needs a multi-page database to truncate meaningfully"
    with open(path, "r+b") as handle:
        handle.truncate(size // 2)

    # A plain connection (not open_database's WAL mode, which can refuse to even open a badly
    # corrupted file) is enough to demonstrate check_integrity detecting the damage.
    connection = sqlite3.connect(path)
    result = check_integrity(connection, quick=False)
    connection.close()
    assert not result.ok


def test_checkpoint_wal_passive_and_truncate(tmp_path: Path) -> None:
    connection = open_database(tmp_path / "a.db")
    apply_migrations(connection, MIGRATIONS, dry_run=False)
    connection.execute("INSERT INTO items (name) VALUES ('x')")
    passive = checkpoint_wal(connection)
    truncate = checkpoint_wal(connection, truncate=True)
    assert isinstance(passive.busy, bool)
    assert truncate.log_frames >= 0
    connection.close()


def test_vacuum_runs_and_preserves_data(tmp_path: Path) -> None:
    connection = open_database(tmp_path / "a.db")
    apply_migrations(connection, MIGRATIONS, dry_run=False)
    connection.execute("INSERT INTO items (name) VALUES ('keep-me')")
    vacuum(connection)
    rows = connection.execute("SELECT name FROM items").fetchall()
    connection.close()
    assert rows == [("keep-me",)]


def test_vacuum_is_never_invoked_automatically_anywhere_in_src() -> None:
    """VACUUM must stay a manual, deliberate primitive (docs/specs/a4-storage-maintenance.md §7)."""
    src = Path(__file__).resolve().parents[3] / "src" / "home_dns"
    offenders = []
    for path in src.rglob("*.py"):
        if path == src / "storage" / "sqlite.py":
            continue  # the definition itself is allowed to call connection.execute("VACUUM")
        text = path.read_text(encoding="utf-8")
        if "vacuum(" in text.lower() or '"vacuum"' in text.lower():
            offenders.append(str(path.relative_to(src)))
    assert not offenders, offenders
