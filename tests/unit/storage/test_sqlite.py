from pathlib import Path

import pytest

from home_dns.storage.sqlite import Migration, MigrationError, apply_migrations, open_database

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
