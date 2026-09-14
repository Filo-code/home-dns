"""Pure monitoring decision models: incident debouncing, restart budgets, freshness escalation.

No I/O — persistence lives in ``storage/monitoring.py``, and nothing here sends a Telegram
message. See docs/specs/a5-monitoring.md for the full design and the transition table this module
implements.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Severity = Literal["critical", "warning", "info"]


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CheckStatus(StrEnum):
    OK = "ok"
    PROBLEM = "problem"


class IncidentState(StrEnum):
    OK = "ok"
    SUSPECT = "suspect"
    INCIDENT = "incident"
    RECOVERING = "recovering"


class TransitionKind(StrEnum):
    NONE = "none"
    OPENED = "opened"  # fire exactly once, entering INCIDENT
    REMINDER = "reminder"  # optional repeat while still INCIDENT, gated by cooldown_seconds
    RECOVERED = "recovered"  # fire exactly once, returning to OK


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: CheckStatus
    detail: str = ""


class IncidentPolicy(_Model):
    incident_after: int = Field(default=2, ge=1)
    recovered_after: int = Field(default=1, ge=1)
    cooldown_seconds: float = Field(default=0, ge=0)


DEFAULT_INCIDENT_POLICY = IncidentPolicy()


@dataclass(frozen=True)
class Incident:
    check_name: str
    state: IncidentState = IncidentState.OK
    consecutive_problem: int = 0
    consecutive_ok: int = 0
    opened_at: datetime | None = None
    last_change_at: datetime | None = None
    last_notified_at: datetime | None = None


def advance_incident(
    previous: Incident, result: CheckResult, *, policy: IncidentPolicy, now: datetime
) -> tuple[Incident, TransitionKind]:
    """Total, deterministic. See docs/specs/a5-monitoring.md §2 for the transition table."""
    if result.name != previous.check_name:
        raise ValueError(f"check name mismatch: {previous.check_name!r} vs {result.name!r}")

    if result.status is CheckStatus.PROBLEM:
        streak = previous.consecutive_problem + 1

        if previous.state in (IncidentState.OK, IncidentState.SUSPECT):
            if streak >= policy.incident_after:
                opened = Incident(
                    previous.check_name, IncidentState.INCIDENT, streak, 0, now, now, now
                )
                return opened, TransitionKind.OPENED
            suspect = Incident(
                previous.check_name,
                IncidentState.SUSPECT,
                streak,
                0,
                None,
                now,
                previous.last_notified_at,
            )
            return suspect, TransitionKind.NONE

        if previous.state is IncidentState.INCIDENT:
            still_open = replace(
                previous, consecutive_problem=streak, consecutive_ok=0, last_change_at=now
            )
            due = (
                policy.cooldown_seconds > 0
                and previous.last_notified_at is not None
                and (now - previous.last_notified_at).total_seconds() >= policy.cooldown_seconds
            )
            if due:
                return replace(still_open, last_notified_at=now), TransitionKind.REMINDER
            return still_open, TransitionKind.NONE

        # RECOVERING relapses straight back to INCIDENT — it was already confirmed, no re-suspect,
        # and no new alert (the open alert already fired and was never followed by a recovery one).
        relapsed = Incident(
            previous.check_name,
            IncidentState.INCIDENT,
            streak,
            0,
            previous.opened_at,
            now,
            previous.last_notified_at,
        )
        return relapsed, TransitionKind.NONE

    # status is CheckStatus.OK
    if previous.state in (IncidentState.OK, IncidentState.SUSPECT):
        # A single good result silently clears SUSPECT — this is the flapping guard.
        return Incident(previous.check_name), TransitionKind.NONE

    ok_streak = previous.consecutive_ok + 1
    if ok_streak >= policy.recovered_after:
        recovered = Incident(previous.check_name, IncidentState.OK, 0, 0, None, now, now)
        return recovered, TransitionKind.RECOVERED
    recovering = replace(
        previous,
        state=IncidentState.RECOVERING,
        consecutive_ok=ok_streak,
        consecutive_problem=0,
        last_change_at=now,
    )
    return recovering, TransitionKind.NONE


class BackoffPolicy(_Model):
    max_attempts: int = Field(default=5, ge=1)
    base_delay_seconds: float = Field(default=1.0, gt=0)
    max_delay_seconds: float = Field(default=300.0, gt=0)
    backoff_factor: float = Field(default=2.0, ge=1)

    @model_validator(mode="after")
    def _delay_bounds_ordered(self) -> BackoffPolicy:
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("max_delay_seconds must be >= base_delay_seconds")
        return self


DEFAULT_BACKOFF_POLICY = BackoffPolicy()


@dataclass(frozen=True)
class RestartBudget:
    attempts: int = 0
    exhausted: bool = False


def advance_restart_budget(
    previous: RestartBudget, *, policy: BackoffPolicy
) -> tuple[RestartBudget, float | None]:
    """Call after a failed attempt. Returns the updated budget and the delay before the next
    retry — ``None`` means the budget is exhausted and the caller must stop restarting."""
    if previous.exhausted:
        return previous, None
    attempts = previous.attempts + 1
    if attempts >= policy.max_attempts:
        return RestartBudget(attempts=attempts, exhausted=True), None
    delay = min(
        policy.base_delay_seconds * (policy.backoff_factor ** (attempts - 1)),
        policy.max_delay_seconds,
    )
    return RestartBudget(attempts=attempts, exhausted=False), delay


def reset_restart_budget() -> RestartBudget:
    return RestartBudget()


@dataclass(frozen=True)
class FreshnessCounter:
    """Per-source count of consecutive pipeline runs that kept the previous artifact."""

    source_id: str
    consecutive_kept_previous: int = 0


def advance_freshness(previous: FreshnessCounter, *, kept_previous: bool) -> FreshnessCounter:
    """Owner-approved ladder (2026-09-13): any non-``kept_previous`` outcome resets to 0."""
    if not kept_previous:
        return FreshnessCounter(previous.source_id, 0)
    return FreshnessCounter(previous.source_id, previous.consecutive_kept_previous + 1)


def freshness_severity(streak: int) -> Severity | None:
    """1st/2nd consecutive kept-previous run -> warning, 3rd+ -> critical, 0 -> no alert.

    The per-run "warning" alert for streak 1-2 is already raised by the pipeline itself
    (``blocklist_update_failure`` / ``suspicious_blocklist``); this only decides when the
    escalation crosses into critical territory.
    """
    if streak <= 0:
        return None
    return "critical" if streak >= 3 else "warning"
