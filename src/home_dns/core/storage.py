"""Pure storage-policy models and decisions: thresholds, retention, cleanup planning.

No I/O. Filesystem reads live in ``storage/disk.py``; mutation (sweeping, pruning, backing up)
lives in the other ``storage/*`` modules. This module only decides, from numbers it is given,
what state the system is in and what should happen — the same split as ``core.policy`` (decides)
versus the pipeline (does).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ThresholdState(StrEnum):
    HEALTHY = "healthy"
    WARNING = "warning"
    AUTO_CLEANUP = "auto_cleanup"
    EMERGENCY = "emergency"


class CleanupActionKind(StrEnum):
    NONE = "none"
    ROUTINE = "routine"
    AGGRESSIVE = "aggressive"


# Maps a threshold band to the event name Telegram alerting (A5/A6) is expected to raise, per
# config/telegram/alerts.yaml. None means "no alert": HEALTHY and WARNING-band recovery are silent
# except for the WARNING event itself, which fires once on entry (A5's job to debounce/track).
_EVENT_FOR_STATE: dict[ThresholdState, str | None] = {
    ThresholdState.HEALTHY: None,
    ThresholdState.WARNING: "storage_above_70",
    ThresholdState.AUTO_CLEANUP: "storage_above_80",
    ThresholdState.EMERGENCY: "storage_above_90",
}

_ACTION_FOR_STATE: dict[ThresholdState, CleanupActionKind] = {
    ThresholdState.HEALTHY: CleanupActionKind.NONE,
    ThresholdState.WARNING: CleanupActionKind.NONE,
    ThresholdState.AUTO_CLEANUP: CleanupActionKind.ROUTINE,
    ThresholdState.EMERGENCY: CleanupActionKind.AGGRESSIVE,
}


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DiskUsage(_Model):
    total_bytes: int = Field(ge=0)
    used_bytes: int = Field(ge=0)
    free_bytes: int = Field(ge=0)

    @model_validator(mode="after")
    def _consistent(self) -> DiskUsage:
        if self.used_bytes > self.total_bytes:
            raise ValueError("used_bytes cannot exceed total_bytes")
        return self

    @property
    def used_percent(self) -> float:
        if self.total_bytes == 0:
            return 0.0
        return round(100 * self.used_bytes / self.total_bytes, 2)


class StorageThresholds(_Model):
    """Percent boundaries. HEALTHY < warning_from <= WARNING < auto_cleanup_from <= ..."""

    healthy_below: float = Field(ge=0, le=100)
    warning_from: float = Field(ge=0, le=100)
    auto_cleanup_from: float = Field(ge=0, le=100)
    emergency_from: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _ordered(self) -> StorageThresholds:
        values = (
            self.healthy_below,
            self.warning_from,
            self.auto_cleanup_from,
            self.emergency_from,
        )
        if self.healthy_below != self.warning_from:
            raise ValueError(
                "healthy_below must equal warning_from (healthy ends where warning starts)"
            )
        if list(values[1:]) != sorted(values[1:]):
            raise ValueError(
                "thresholds must be non-decreasing: warning <= auto_cleanup <= emergency"
            )
        return self


DEFAULT_THRESHOLDS = StorageThresholds(
    healthy_below=70, warning_from=70, auto_cleanup_from=80, emergency_from=90
)


def classify_usage(usage: DiskUsage, thresholds: StorageThresholds) -> ThresholdState:
    """Total function: every percentage in [0, 100] maps to exactly one band."""
    percent = usage.used_percent
    if percent >= thresholds.emergency_from:
        return ThresholdState.EMERGENCY
    if percent >= thresholds.auto_cleanup_from:
        return ThresholdState.AUTO_CLEANUP
    if percent >= thresholds.warning_from:
        return ThresholdState.WARNING
    return ThresholdState.HEALTHY


def storage_event_for(state: ThresholdState) -> str | None:
    return _EVENT_FOR_STATE[state]


def cleanup_action_for(state: ThresholdState) -> CleanupActionKind:
    return _ACTION_FOR_STATE[state]


class RetentionPolicy(_Model):
    logs_max_bytes: int = Field(ge=1024)
    logs_backup_count: int = Field(ge=1, le=100)
    temp_max_age_hours: float = Field(gt=0)
    backups_keep: int = Field(ge=1, le=1000)
    query_history_days: int = Field(ge=1, le=3650)


DEFAULT_RETENTION = RetentionPolicy(
    logs_max_bytes=10 * 1024 * 1024,
    logs_backup_count=5,
    temp_max_age_hours=24,
    backups_keep=7,
    query_history_days=30,
)


class CategoryUsage(_Model):
    name: str = Field(min_length=1)
    path: str
    bytes: int = Field(ge=0)
    exists: bool


class StorageReport(_Model):
    """The clean, provider-neutral snapshot A5 monitoring is expected to consume."""

    checked_at: datetime
    disk: DiskUsage
    state: ThresholdState
    categories: tuple[CategoryUsage, ...] = ()
    last_cleanup_at: datetime | None = None
    last_backup_at: datetime | None = None
    backup_count: int = Field(default=0, ge=0)
    artifact_counts: dict[str, int] = Field(default_factory=dict)

    @property
    def event(self) -> str | None:
        return storage_event_for(self.state)

    @property
    def recommended_action(self) -> CleanupActionKind:
        return cleanup_action_for(self.state)

    @property
    def backup_age_seconds(self) -> float | None:
        if self.last_backup_at is None:
            return None
        return (self.checked_at - self.last_backup_at).total_seconds()


@dataclass(frozen=True)
class CleanupStepPlan:
    """One planned action, before execution. ``target`` is a category name, for reporting."""

    target: str
    description: str


@dataclass(frozen=True)
class CleanupPlan:
    state: ThresholdState
    action: CleanupActionKind
    steps: tuple[CleanupStepPlan, ...]


def plan_cleanup(state: ThresholdState) -> CleanupPlan:
    """Decide *which categories* need action for a given band. Execution is storage/cleanup.py."""
    action = cleanup_action_for(state)
    if action is CleanupActionKind.NONE:
        return CleanupPlan(state, action, ())
    if action is CleanupActionKind.AGGRESSIVE:
        steps = (
            CleanupStepPlan("tmp", "sweep all temporary files regardless of age"),
            CleanupStepPlan("backups", "prune backups to a single newest valid backup"),
            CleanupStepPlan("blocklists", "reconcile blocklist artifact stores (prune orphans)"),
        )
    else:
        steps = (
            CleanupStepPlan("tmp", "sweep temporary files older than the configured age"),
            CleanupStepPlan("backups", "prune backups beyond the retention count"),
            CleanupStepPlan("blocklists", "reconcile blocklist artifact stores (prune orphans)"),
        )
    return CleanupPlan(state, action, steps)


@dataclass(frozen=True)
class CleanupStepResult:
    target: str
    description: str
    removed: tuple[str, ...]
    dry_run: bool


@dataclass(frozen=True)
class CleanupResult:
    plan: CleanupPlan
    steps: tuple[CleanupStepResult, ...]

    @property
    def total_removed(self) -> int:
        return sum(len(s.removed) for s in self.steps)
