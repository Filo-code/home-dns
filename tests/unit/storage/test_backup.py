import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from home_dns.storage.backup import (
    BackupError,
    create_backup,
    list_backups,
    prune_backups,
    restore_backup,
    verify_backup,
)

NOW = datetime(2026, 9, 14, 12, 0, 0, tzinfo=UTC)


def _make_source(tmp_path: Path, name: str, files: dict[str, bytes]) -> Path:
    root = tmp_path / name
    for relative, data in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return root


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    src = _make_source(tmp_path, "config", {"a.yaml": b"hello"})
    dest = tmp_path / "backups"
    result = create_backup({"config": src}, dest, now=NOW, dry_run=True)
    assert result.dry_run and len(result.manifest.entries) == 1
    assert not dest.exists()


def test_create_then_verify_round_trip(tmp_path: Path) -> None:
    src = _make_source(tmp_path, "config", {"a.yaml": b"hello", "sub/b.yaml": b"world"})
    dest = tmp_path / "backups"
    result = create_backup({"config": src}, dest, now=NOW, dry_run=False)
    assert result.path.is_dir()
    assert (result.path / "manifest.json").is_file()
    assert len(result.manifest.entries) == 2
    verification = verify_backup(result.path)
    assert verification.ok and verification.checked == 2
    assert not list(dest.glob(".*.tmp"))  # no leftover temp directory


def test_restore_is_byte_identical(tmp_path: Path) -> None:
    src = _make_source(tmp_path, "config", {"a.yaml": b"original content\n"})
    dest = tmp_path / "backups"
    result = create_backup({"config": src}, dest, now=NOW, dry_run=False)
    target = tmp_path / "restored"
    restore_result = restore_backup(result.path, {"config": target}, dry_run=False)
    assert restore_result.restored == ("config/a.yaml",)
    assert (target / "a.yaml").read_bytes() == (src / "a.yaml").read_bytes()


def test_restore_dry_run_writes_nothing(tmp_path: Path) -> None:
    src = _make_source(tmp_path, "config", {"a.yaml": b"data"})
    dest = tmp_path / "backups"
    result = create_backup({"config": src}, dest, now=NOW, dry_run=False)
    target = tmp_path / "restored"
    restore_backup(result.path, {"config": target}, dry_run=True)
    assert not target.exists()


def test_verify_detects_tampered_file(tmp_path: Path) -> None:
    src = _make_source(tmp_path, "config", {"a.yaml": b"data"})
    dest = tmp_path / "backups"
    result = create_backup({"config": src}, dest, now=NOW, dry_run=False)
    (result.path / "config" / "a.yaml").write_bytes(b"tampered")
    verification = verify_backup(result.path)
    assert not verification.ok
    assert verification.mismatches[0].reason == "checksum mismatch"


def test_verify_detects_missing_file(tmp_path: Path) -> None:
    src = _make_source(tmp_path, "config", {"a.yaml": b"data"})
    dest = tmp_path / "backups"
    result = create_backup({"config": src}, dest, now=NOW, dry_run=False)
    (result.path / "config" / "a.yaml").unlink()
    verification = verify_backup(result.path)
    assert verification.mismatches[0].reason == "missing"


def test_restore_refuses_when_verification_fails(tmp_path: Path) -> None:
    src = _make_source(tmp_path, "config", {"a.yaml": b"data"})
    dest = tmp_path / "backups"
    result = create_backup({"config": src}, dest, now=NOW, dry_run=False)
    (result.path / "config" / "a.yaml").write_bytes(b"tampered")
    target = tmp_path / "restored"
    with pytest.raises(BackupError, match="verification failed"):
        restore_backup(result.path, {"config": target}, dry_run=False)
    assert not target.exists()


def test_verify_missing_manifest_raises(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backup-20260914T000000Z"
    backup_dir.mkdir()
    with pytest.raises(BackupError, match="manifest"):
        verify_backup(backup_dir)


def test_list_backups_ignores_non_matching_directories(tmp_path: Path) -> None:
    dest = tmp_path / "backups"
    dest.mkdir()
    (dest / "not-a-backup").mkdir()
    (dest / "backup-20260914T000000Z").mkdir()
    (dest / "backup-20260914T000000Z" / "manifest.json").write_text(
        json.dumps({"created_at": NOW.isoformat(), "entries": []})
    )
    infos = list_backups(dest)
    assert [i.name for i in infos] == ["backup-20260914T000000Z"]


def test_list_backups_reports_invalid_without_deleting(tmp_path: Path) -> None:
    dest = tmp_path / "backups"
    incomplete = dest / "backup-20260914T000000Z"
    incomplete.mkdir(parents=True)
    (incomplete / "config").mkdir()
    (incomplete / "config" / "a.yaml").write_bytes(b"orphaned")
    infos = list_backups(dest)
    assert len(infos) == 1 and not infos[0].valid and infos[0].error == "missing manifest.json"
    assert incomplete.exists()  # never deleted by list_backups


def test_missing_destination_lists_nothing(tmp_path: Path) -> None:
    assert list_backups(tmp_path / "nope") == []


def _create_at(tmp_path: Path, dest: Path, offset_seconds: int, content: bytes = b"x") -> Path:
    src = _make_source(tmp_path, f"src-{offset_seconds}", {"a.yaml": content})
    return create_backup(
        {"config": src}, dest, now=NOW + timedelta(seconds=offset_seconds), dry_run=False
    ).path


def test_prune_keeps_newest_n(tmp_path: Path) -> None:
    dest = tmp_path / "backups"
    for i in range(5):
        _create_at(tmp_path, dest, i)
    result = prune_backups(dest, keep=2, dry_run=False)
    remaining = {i.name for i in list_backups(dest)}
    assert len(remaining) == 2
    assert set(result.kept) == remaining


def test_prune_never_removes_single_newest_valid_even_if_keep_is_zero(tmp_path: Path) -> None:
    dest = tmp_path / "backups"
    for i in range(3):
        _create_at(tmp_path, dest, i)
    result = prune_backups(dest, keep=0, dry_run=False)
    assert len(list_backups(dest)) == 1
    assert len(result.kept) == 1


def test_prune_dry_run_deletes_nothing(tmp_path: Path) -> None:
    dest = tmp_path / "backups"
    for i in range(4):
        _create_at(tmp_path, dest, i)
    before = {i.name for i in list_backups(dest)}
    result = prune_backups(dest, keep=1, dry_run=True)
    after = {i.name for i in list_backups(dest)}
    assert before == after
    assert len(result.removed) == 3


def test_prune_is_idempotent(tmp_path: Path) -> None:
    dest = tmp_path / "backups"
    for i in range(4):
        _create_at(tmp_path, dest, i)
    prune_backups(dest, keep=2, dry_run=False)
    second = prune_backups(dest, keep=2, dry_run=False)
    assert second.removed == ()


def test_prune_only_touches_backup_named_directories(tmp_path: Path) -> None:
    dest = tmp_path / "backups"
    for i in range(3):
        _create_at(tmp_path, dest, i)
    foreign = dest / "not-a-backup-dir"
    foreign.mkdir()
    (foreign / "important.txt").write_text("keep me")
    prune_backups(dest, keep=1, dry_run=False)
    assert foreign.exists() and (foreign / "important.txt").exists()


def test_prune_removes_invalid_backups_older_than_newest_valid(tmp_path: Path) -> None:
    dest = tmp_path / "backups"
    valid = _create_at(tmp_path, dest, 10)
    broken = dest / "backup-20260101T000000Z"  # older than `valid`, no manifest
    broken.mkdir()
    result = prune_backups(dest, keep=1, dry_run=False)
    assert broken.name in result.removed
    assert valid.exists()


def test_backup_error_on_invalid_source_name(tmp_path: Path) -> None:
    with pytest.raises(BackupError, match="invalid source name"):
        create_backup({"Not Valid": tmp_path}, tmp_path / "backups", now=NOW)


def test_interrupted_backup_leaves_no_trace_in_list_backups(tmp_path: Path) -> None:
    """A crash before the final manifest write / rename is simulated by leaving a .tmp dir."""
    dest = tmp_path / "backups"
    dest.mkdir()
    leftover = dest / ".backup-20260914T000000Z.tmp"
    leftover.mkdir()
    (leftover / "partial").write_bytes(b"incomplete")
    assert list_backups(dest) == []  # the crashed attempt is invisible, not corrupting anything


def test_creating_same_timestamp_twice_fails_loudly_not_silently(tmp_path: Path) -> None:
    src = _make_source(tmp_path, "config", {"a.yaml": b"first"})
    dest = tmp_path / "backups"
    create_backup({"config": src}, dest, now=NOW, dry_run=False)
    with pytest.raises(BackupError, match="already exists"):
        create_backup({"config": src}, dest, now=NOW, dry_run=False)
    # the original backup is untouched
    assert verify_backup(dest / "backup-20260914T120000Z").ok
