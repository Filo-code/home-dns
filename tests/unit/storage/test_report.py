from datetime import UTC, datetime
from pathlib import Path

from home_dns.core.storage import DEFAULT_THRESHOLDS, DiskUsage, ThresholdState
from home_dns.storage.artifacts import ArtifactStore
from home_dns.storage.backup import create_backup
from home_dns.storage.report import build_storage_report

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)


class _FakeDisk:
    def __init__(self, usage: DiskUsage) -> None:
        self._usage = usage

    def get(self, path: Path) -> DiskUsage:
        return self._usage


def test_report_composes_disk_categories_backups_and_artifacts(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    log_dir = tmp_path / "logs"
    backup_dir = tmp_path / "backups"
    (data_dir).mkdir()
    (data_dir / "a.db").write_bytes(b"x" * 100)
    log_dir.mkdir()
    (log_dir / "app.log").write_bytes(b"y" * 50)

    store = ArtifactStore(data_dir / "blocklists")
    store.activate("list-a", "content-v1\n", {}, dry_run=False)
    (tmp_path / "cfg").mkdir()
    (tmp_path / "cfg" / "x.yaml").write_text("a: 1\n")
    create_backup({"config": tmp_path / "cfg"}, backup_dir, now=NOW, dry_run=False)

    disk = _FakeDisk(DiskUsage(total_bytes=1000, used_bytes=850, free_bytes=150))
    report = build_storage_report(
        root=data_dir,
        categories={"data": data_dir, "logs": log_dir, "backups": backup_dir},
        disk=disk,
        thresholds=DEFAULT_THRESHOLDS,
        backup_dir=backup_dir,
        artifact_store=store,
        artifact_sources=["list-a"],
        now=NOW,
    )
    assert report.state is ThresholdState.AUTO_CLEANUP
    assert report.disk.used_percent == 85.0
    by_name = {c.name: c for c in report.categories}
    assert by_name["logs"].bytes == 50 and by_name["logs"].exists
    assert report.backup_count == 1
    assert report.last_backup_at == NOW
    assert report.artifact_counts == {"list-a": 1}


def test_report_missing_category_directory_is_reported_not_erroring(tmp_path: Path) -> None:
    disk = _FakeDisk(DiskUsage(total_bytes=1000, used_bytes=100, free_bytes=900))
    report = build_storage_report(
        root=tmp_path,
        categories={"tmp": tmp_path / "nonexistent"},
        disk=disk,
        thresholds=DEFAULT_THRESHOLDS,
        backup_dir=tmp_path / "no-backups",
        artifact_store=None,
        now=NOW,
    )
    assert report.categories[0].exists is False and report.categories[0].bytes == 0
    assert report.last_backup_at is None and report.backup_count == 0


def test_report_without_artifact_store_has_empty_counts(tmp_path: Path) -> None:
    disk = _FakeDisk(DiskUsage(total_bytes=1000, used_bytes=10, free_bytes=990))
    report = build_storage_report(
        root=tmp_path,
        categories={},
        disk=disk,
        thresholds=DEFAULT_THRESHOLDS,
        backup_dir=tmp_path,
        artifact_store=None,
        artifact_sources=["list-a"],
        now=NOW,
    )
    assert report.artifact_counts == {}
    assert report.state is ThresholdState.HEALTHY


# ------------------------------------------------------------- A4.1 (RAM/tmpfs audit): tmp_dir


def test_report_tmp_dir_usable_true_when_present_and_writable(tmp_path: Path) -> None:
    tmp_dir = tmp_path / "tmp"
    tmp_dir.mkdir()
    disk = _FakeDisk(DiskUsage(total_bytes=1000, used_bytes=10, free_bytes=990))
    report = build_storage_report(
        root=tmp_path,
        categories={},
        disk=disk,
        thresholds=DEFAULT_THRESHOLDS,
        backup_dir=tmp_path,
        artifact_store=None,
        tmp_dir=tmp_dir,
        now=NOW,
    )
    assert report.tmp_dir_usable is True


def test_report_tmp_dir_usable_false_when_missing(tmp_path: Path) -> None:
    disk = _FakeDisk(DiskUsage(total_bytes=1000, used_bytes=10, free_bytes=990))
    report = build_storage_report(
        root=tmp_path,
        categories={},
        disk=disk,
        thresholds=DEFAULT_THRESHOLDS,
        backup_dir=tmp_path,
        artifact_store=None,
        tmp_dir=tmp_path / "unmounted",
        now=NOW,
    )
    assert report.tmp_dir_usable is False
    assert not (tmp_path / "unmounted").exists()  # checking status never creates it


def test_report_tmp_dir_usable_defaults_true_when_not_checked(tmp_path: Path) -> None:
    disk = _FakeDisk(DiskUsage(total_bytes=1000, used_bytes=10, free_bytes=990))
    report = build_storage_report(
        root=tmp_path,
        categories={},
        disk=disk,
        thresholds=DEFAULT_THRESHOLDS,
        backup_dir=tmp_path,
        artifact_store=None,
        now=NOW,
    )
    assert report.tmp_dir_usable is True
