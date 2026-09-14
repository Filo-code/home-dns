import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from home_dns.storage.tempfiles import sweep_temp_dir

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
MAX_AGE = timedelta(hours=24)


def _touch(path: Path, *, age: timedelta) -> None:
    path.write_bytes(b"data")
    mtime = (NOW - age).timestamp()
    os.utime(path, (mtime, mtime))


def test_missing_directory_is_a_no_op(tmp_path: Path) -> None:
    result = sweep_temp_dir(tmp_path / "nope", max_age=MAX_AGE, now=NOW)
    assert result.removed == () and result.skipped == ()


def test_old_files_are_removed_young_files_kept(tmp_path: Path) -> None:
    _touch(tmp_path / "old.tmp", age=timedelta(hours=25))
    _touch(tmp_path / "young.tmp", age=timedelta(hours=1))
    result = sweep_temp_dir(tmp_path, max_age=MAX_AGE, now=NOW, dry_run=False)
    assert result.removed == ("old.tmp",)
    assert (tmp_path / "young.tmp").exists()
    assert not (tmp_path / "old.tmp").exists()


def test_exactly_at_max_age_is_removed(tmp_path: Path) -> None:
    """Boundary: age >= max_age is the removal condition."""
    _touch(tmp_path / "boundary.tmp", age=MAX_AGE)
    result = sweep_temp_dir(tmp_path, max_age=MAX_AGE, now=NOW, dry_run=False)
    assert result.removed == ("boundary.tmp",)


def test_just_under_max_age_is_kept(tmp_path: Path) -> None:
    _touch(tmp_path / "young.tmp", age=MAX_AGE - timedelta(seconds=1))
    result = sweep_temp_dir(tmp_path, max_age=MAX_AGE, now=NOW, dry_run=False)
    assert result.removed == ()


def test_dry_run_does_not_delete(tmp_path: Path) -> None:
    _touch(tmp_path / "old.tmp", age=timedelta(hours=48))
    result = sweep_temp_dir(tmp_path, max_age=MAX_AGE, now=NOW, dry_run=True)
    assert result.dry_run and result.removed == ("old.tmp",)
    assert (tmp_path / "old.tmp").exists()


def test_idempotent_second_run_removes_nothing_new(tmp_path: Path) -> None:
    _touch(tmp_path / "old.tmp", age=timedelta(hours=48))
    sweep_temp_dir(tmp_path, max_age=MAX_AGE, now=NOW, dry_run=False)
    second = sweep_temp_dir(tmp_path, max_age=MAX_AGE, now=NOW, dry_run=False)
    assert second.removed == ()


def test_symlink_is_skipped_not_deleted(tmp_path: Path) -> None:
    target = tmp_path.parent / "outside-target.tmp"
    target.write_bytes(b"keep me")
    link = tmp_path / "link.tmp"
    link.symlink_to(target)
    os.utime(link, ((NOW - timedelta(hours=48)).timestamp(),) * 2, follow_symlinks=False)
    result = sweep_temp_dir(tmp_path, max_age=MAX_AGE, now=NOW, dry_run=False)
    assert result.removed == ()
    assert result.skipped == (("link.tmp", "symlink"),)
    assert target.exists()


def test_subdirectory_is_skipped_not_descended_into(tmp_path: Path) -> None:
    nested = tmp_path / "subdir"
    nested.mkdir()
    _touch(nested / "old.tmp", age=timedelta(hours=48))
    result = sweep_temp_dir(tmp_path, max_age=MAX_AGE, now=NOW, dry_run=False)
    assert result.removed == ()
    assert (nested / "old.tmp").exists()


def test_empty_directory_sweeps_cleanly(tmp_path: Path) -> None:
    result = sweep_temp_dir(tmp_path, max_age=MAX_AGE, now=NOW, dry_run=False)
    assert result.removed == () and result.skipped == ()


def test_delete_failure_is_reported_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _touch(tmp_path / "stuck.tmp", age=timedelta(hours=48))

    def refuse(self: Path, missing_ok: bool = False) -> None:
        raise PermissionError("simulated: read-only filesystem")

    monkeypatch.setattr(Path, "unlink", refuse)
    result = sweep_temp_dir(tmp_path, max_age=MAX_AGE, now=NOW, dry_run=False)
    monkeypatch.undo()
    assert result.removed == ()
    assert result.skipped == (("stuck.tmp", "delete failed"),)
    assert (tmp_path / "stuck.tmp").exists()
