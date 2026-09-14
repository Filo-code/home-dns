from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from home_dns.core.storage import (
    DEFAULT_RETENTION,
    DEFAULT_THRESHOLDS,
    CleanupActionKind,
    DiskUsage,
    RetentionPolicy,
    StorageReport,
    StorageThresholds,
    ThresholdState,
    classify_usage,
    cleanup_action_for,
    plan_cleanup,
    storage_event_for,
)

NOW = datetime(2026, 9, 14, tzinfo=UTC)


def _usage(percent: float, total: int = 1000) -> DiskUsage:
    used = round(total * percent / 100)
    return DiskUsage(total_bytes=total, used_bytes=used, free_bytes=total - used)


@pytest.mark.parametrize(
    ("percent", "expected"),
    [
        (0, ThresholdState.HEALTHY),
        (69.99, ThresholdState.HEALTHY),
        (70, ThresholdState.WARNING),  # exactly 70%
        (75, ThresholdState.WARNING),
        (79.99, ThresholdState.WARNING),
        (80, ThresholdState.AUTO_CLEANUP),  # exactly 80%
        (85, ThresholdState.AUTO_CLEANUP),
        (89.99, ThresholdState.AUTO_CLEANUP),
        (90, ThresholdState.EMERGENCY),  # exactly 90%
        (95, ThresholdState.EMERGENCY),
        (100, ThresholdState.EMERGENCY),
    ],
)
def test_classify_usage_every_boundary(percent: float, expected: ThresholdState) -> None:
    assert classify_usage(_usage(percent, total=10_000), DEFAULT_THRESHOLDS) is expected


def test_classify_usage_is_total_across_the_whole_range() -> None:
    for tenth in range(0, 1001):
        state = classify_usage(_usage(tenth / 10, total=100_000), DEFAULT_THRESHOLDS)
        assert isinstance(state, ThresholdState)


def test_classify_usage_empty_filesystem_is_healthy() -> None:
    assert classify_usage(
        DiskUsage(total_bytes=0, used_bytes=0, free_bytes=0), DEFAULT_THRESHOLDS
    ) is (ThresholdState.HEALTHY)


def test_disk_usage_rejects_used_over_total() -> None:
    with pytest.raises(ValidationError):
        DiskUsage(total_bytes=10, used_bytes=11, free_bytes=0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"healthy_below": 70, "warning_from": 71, "auto_cleanup_from": 80, "emergency_from": 90},
        {"healthy_below": 70, "warning_from": 70, "auto_cleanup_from": 60, "emergency_from": 90},
        {"healthy_below": 70, "warning_from": 70, "auto_cleanup_from": 90, "emergency_from": 80},
        {"healthy_below": 70, "warning_from": 70, "auto_cleanup_from": 80, "emergency_from": 101},
    ],
)
def test_invalid_threshold_ordering_is_rejected(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValidationError):
        StorageThresholds(**kwargs)


def test_equal_thresholds_are_allowed() -> None:
    thresholds = StorageThresholds(
        healthy_below=80, warning_from=80, auto_cleanup_from=80, emergency_from=80
    )
    assert classify_usage(_usage(80, total=1000), thresholds) is ThresholdState.EMERGENCY
    assert classify_usage(_usage(79, total=1000), thresholds) is ThresholdState.HEALTHY


@pytest.mark.parametrize(
    "overrides",
    [
        {"logs_max_bytes": 0},
        {"logs_backup_count": 0},
        {"temp_max_age_hours": 0},
        {"backups_keep": 0},
        {"query_history_days": 0},
    ],
)
def test_invalid_retention_values_are_rejected(overrides: dict[str, int]) -> None:
    values = DEFAULT_RETENTION.model_dump()
    values.update(overrides)
    with pytest.raises(ValidationError):
        RetentionPolicy(**values)


@pytest.mark.parametrize(
    ("state", "event", "action"),
    [
        (ThresholdState.HEALTHY, None, CleanupActionKind.NONE),
        (ThresholdState.WARNING, "storage_above_70", CleanupActionKind.NONE),
        (ThresholdState.AUTO_CLEANUP, "storage_above_80", CleanupActionKind.ROUTINE),
        (ThresholdState.EMERGENCY, "storage_above_90", CleanupActionKind.AGGRESSIVE),
    ],
)
def test_event_and_action_per_state(
    state: ThresholdState, event: str | None, action: CleanupActionKind
) -> None:
    assert storage_event_for(state) == event
    assert cleanup_action_for(state) is action


def test_plan_cleanup_healthy_and_warning_have_no_steps() -> None:
    assert plan_cleanup(ThresholdState.HEALTHY).steps == ()
    assert plan_cleanup(ThresholdState.WARNING).steps == ()


def test_plan_cleanup_auto_cleanup_targets_all_three_categories() -> None:
    plan = plan_cleanup(ThresholdState.AUTO_CLEANUP)
    assert [s.target for s in plan.steps] == ["tmp", "backups", "blocklists"]
    assert "older than" in plan.steps[0].description


def test_plan_cleanup_emergency_is_more_aggressive_in_wording() -> None:
    plan = plan_cleanup(ThresholdState.EMERGENCY)
    assert plan.action is CleanupActionKind.AGGRESSIVE
    assert "regardless of age" in plan.steps[0].description
    assert "single newest" in plan.steps[1].description


def test_storage_report_event_and_action_and_backup_age() -> None:
    report = StorageReport(
        checked_at=NOW,
        disk=_usage(85, total=1000),
        state=ThresholdState.AUTO_CLEANUP,
        last_backup_at=datetime(2026, 9, 13, tzinfo=UTC),
    )
    assert report.event == "storage_above_80"
    assert report.recommended_action is CleanupActionKind.ROUTINE
    assert report.backup_age_seconds == pytest.approx(86400.0)


def test_storage_report_no_backup_has_no_age() -> None:
    report = StorageReport(checked_at=NOW, disk=_usage(10), state=ThresholdState.HEALTHY)
    assert report.backup_age_seconds is None
