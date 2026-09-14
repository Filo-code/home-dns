from collections.abc import Callable
from pathlib import Path

import pytest

from home_dns.config.loader import ConfigLoadError
from home_dns.config.storage import load_storage_config, storage_config_files
from tests.conftest import DEV_PROFILE

MakeConfigDir = Callable[..., Path]


def test_repository_storage_config_matches_owner_approved_thresholds(repo_config_dir: Path) -> None:
    config = load_storage_config(repo_config_dir)
    t = config.thresholds
    assert (t.healthy_below, t.warning_from, t.auto_cleanup_from, t.emergency_from) == (
        70,
        70,
        80,
        90,
    )
    r = config.retention
    assert r.query_history_days == 30
    assert r.backups_keep >= 1


def test_fixture_storage_config_is_valid(make_config_dir: MakeConfigDir) -> None:
    config = load_storage_config(make_config_dir(DEV_PROFILE))
    assert config.thresholds.warning_from == 70


def test_missing_storage_file_is_a_load_error(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE, storage=False)
    with pytest.raises(ConfigLoadError, match="file not found"):
        load_storage_config(config_dir)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("schema_version: 2\n", "schema_version"),
        ("schema_version: 1\n", "disk_usage_thresholds_percent"),
        (
            "schema_version: 1\ndisk_usage_thresholds_percent: {healthy_below: 70, "
            "warning_from: 70, auto_cleanup_from: 60, emergency_from: 90}\n"
            "retention: {logs_max_bytes: 1024, logs_backup_count: 1, temp_max_age_hours: 1, "
            "backups_keep: 1, query_history_days: 1}\n",
            "non-decreasing",
        ),
        (
            "schema_version: 1\ndisk_usage_thresholds_percent: {healthy_below: 70, "
            "warning_from: 60, auto_cleanup_from: 80, emergency_from: 90}\n"
            "retention: {logs_max_bytes: 1024, logs_backup_count: 1, temp_max_age_hours: 1, "
            "backups_keep: 1, query_history_days: 1}\n",
            "must equal warning_from",
        ),
        (
            "schema_version: 1\ndisk_usage_thresholds_percent: {healthy_below: 70, "
            "warning_from: 70, auto_cleanup_from: 80, emergency_from: 90}\n"
            "retention: {logs_max_bytes: 1024, logs_backup_count: 1, temp_max_age_hours: 1, "
            "backups_keep: 0, query_history_days: 1}\n",
            "backups_keep",
        ),
        (
            "schema_version: 1\ndisk_usage_thresholds_percent: {healthy_below: 70, "
            "warning_from: 70, auto_cleanup_from: 80, emergency_from: 90}\n"
            "retention: {logs_max_bytes: 1024, logs_backup_count: 1, temp_max_age_hours: 1, "
            "backups_keep: 1, query_history_days: 1}\nextra: true\n",
            "extra",
        ),
        (
            "schema_version: 1\ndisk_usage_thresholds_percent: {healthy_below: 70, "
            "warning_from: 70, auto_cleanup_from: 80, emergency_from: 90}\n"
            "retention: {logs_max_bytes: 1024, logs_backup_count: 1, temp_max_age_hours: 1, "
            "backups_keep: 1, query_history_days: 1, token: abc}\n",
            "secret-like keys",
        ),
        (
            "schema_version: 1\ndisk_usage_thresholds_percent: '<<TODO>>'\n"
            "retention: {logs_max_bytes: 1024, logs_backup_count: 1, temp_max_age_hours: 1, "
            "backups_keep: 1, query_history_days: 1}\n",
            "malformed placeholder",
        ),
    ],
)
def test_invalid_storage_configs_are_rejected(
    make_config_dir: MakeConfigDir, content: str, message: str
) -> None:
    config_dir = make_config_dir(DEV_PROFILE, **{"storage__storage.yaml": content})
    with pytest.raises(ConfigLoadError, match=message):
        load_storage_config(config_dir)


def test_storage_config_files_returns_the_one_owned_path(repo_config_dir: Path) -> None:
    files = storage_config_files(repo_config_dir)
    assert files == [repo_config_dir / "storage" / "storage.yaml"]
