from datetime import UTC, datetime, timedelta
from pathlib import Path

from home_dns.core.storage import DEFAULT_RETENTION, ThresholdState, plan_cleanup
from home_dns.storage.artifacts import ArtifactStore
from home_dns.storage.backup import create_backup, list_backups
from home_dns.storage.cleanup import execute_cleanup

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)


def _touch_old(path: Path, hours: int) -> None:
    import os

    path.write_bytes(b"x")
    mtime = (NOW - timedelta(hours=hours)).timestamp()
    os.utime(path, (mtime, mtime))


def test_healthy_and_warning_plans_execute_no_steps(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "data" / "blocklists")
    for state in (ThresholdState.HEALTHY, ThresholdState.WARNING):
        plan = plan_cleanup(state)
        result = execute_cleanup(
            plan,
            tmp_dir=tmp_path / "tmp",
            backup_dir=tmp_path / "backups",
            artifact_store=store,
            artifact_sources=[],
            retention=DEFAULT_RETENTION,
            now=NOW,
            dry_run=False,
        )
        assert result.steps == ()
        assert result.total_removed == 0


def test_routine_cleanup_sweeps_old_temp_and_prunes_backups(tmp_path: Path) -> None:
    tmp_dir = tmp_path / "tmp"
    tmp_dir.mkdir(parents=True)
    _touch_old(tmp_dir / "old.tmp", hours=48)
    backup_dir = tmp_path / "backups"
    for i in range(5):
        (tmp_path / f"src{i}").mkdir()
        (tmp_path / f"src{i}" / "a.yaml").write_bytes(b"x")
        create_backup(
            {"config": tmp_path / f"src{i}"},
            backup_dir,
            now=NOW + timedelta(seconds=i),
            dry_run=False,
        )
    store = ArtifactStore(tmp_path / "data" / "blocklists")

    plan = plan_cleanup(ThresholdState.AUTO_CLEANUP)
    result = execute_cleanup(
        plan,
        tmp_dir=tmp_dir,
        backup_dir=backup_dir,
        artifact_store=store,
        artifact_sources=[],
        retention=DEFAULT_RETENTION.model_copy(update={"backups_keep": 2}),
        now=NOW,
        dry_run=False,
    )
    assert not (tmp_dir / "old.tmp").exists()
    assert len(list_backups(backup_dir)) == 2
    targets = {s.target for s in result.steps}
    assert targets == {"tmp", "backups", "blocklists"}


def test_emergency_cleanup_sweeps_regardless_of_age_and_keeps_one_backup(tmp_path: Path) -> None:
    tmp_dir = tmp_path / "tmp"
    tmp_dir.mkdir(parents=True)
    _touch_old(tmp_dir / "brand_new.tmp", hours=0)  # would survive routine cleanup
    backup_dir = tmp_path / "backups"
    for i in range(3):
        (tmp_path / f"src{i}").mkdir()
        (tmp_path / f"src{i}" / "a.yaml").write_bytes(b"x")
        create_backup(
            {"config": tmp_path / f"src{i}"},
            backup_dir,
            now=NOW + timedelta(seconds=i),
            dry_run=False,
        )
    store = ArtifactStore(tmp_path / "data" / "blocklists")

    plan = plan_cleanup(ThresholdState.EMERGENCY)
    execute_cleanup(
        plan,
        tmp_dir=tmp_dir,
        backup_dir=backup_dir,
        artifact_store=store,
        artifact_sources=[],
        retention=DEFAULT_RETENTION,
        now=NOW,
        dry_run=False,
    )
    assert not (tmp_dir / "brand_new.tmp").exists()
    assert len(list_backups(backup_dir)) == 1


def test_dry_run_cleanup_changes_nothing(tmp_path: Path) -> None:
    tmp_dir = tmp_path / "tmp"
    tmp_dir.mkdir(parents=True)
    _touch_old(tmp_dir / "old.tmp", hours=48)
    store = ArtifactStore(tmp_path / "data" / "blocklists")
    plan = plan_cleanup(ThresholdState.EMERGENCY)
    result = execute_cleanup(
        plan,
        tmp_dir=tmp_dir,
        backup_dir=tmp_path / "backups",
        artifact_store=store,
        artifact_sources=[],
        retention=DEFAULT_RETENTION,
        now=NOW,
        dry_run=True,
    )
    assert (tmp_dir / "old.tmp").exists()
    assert result.total_removed == 1  # reported as would-remove, but not actually removed


def test_cleanup_reconciles_blocklist_artifacts(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "data" / "blocklists")
    store.activate("list-a", "v1\n", {}, dry_run=False)
    orphan = tmp_path / "data" / "blocklists" / "list-a" / "artifacts" / f"{'d' * 64}.txt"
    orphan.write_text("orphan\n")
    plan = plan_cleanup(ThresholdState.AUTO_CLEANUP)
    result = execute_cleanup(
        plan,
        tmp_dir=tmp_path / "tmp",
        backup_dir=tmp_path / "backups",
        artifact_store=store,
        artifact_sources=["list-a"],
        retention=DEFAULT_RETENTION,
        now=NOW,
        dry_run=False,
    )
    blocklist_step = next(s for s in result.steps if s.target == "blocklists")
    assert blocklist_step.removed == (f"list-a/{'d' * 64}.txt",)
    assert not orphan.exists()
    assert store.current("list-a") is not None  # current artifact untouched
