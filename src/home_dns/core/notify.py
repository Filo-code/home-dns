"""Pure alerting decision models: severity routing, Italian message formatting, anti-spam.

No I/O — transport lives in ``notify/*``, persistence in ``storage/notify.py``. See
docs/specs/a6-telegram-alerting.md for the full design.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["critical", "warning", "info"]

_LABEL: dict[Severity, str] = {
    "critical": "🔴 CRITICO",
    "warning": "🟠 AVVISO",
    "info": "ℹ️ INFO",  # noqa: RUF001 (intentional emoji, not a typo'd "i")
}


@dataclass(frozen=True)
class AlertMessage:
    severity: Severity
    event: str
    detail: str


def format_message(alert: AlertMessage) -> str:
    """Italian-language message (owner decision, 2026-09-14)."""
    return f"{_LABEL[alert.severity]} — {alert.event}\n{alert.detail}"


def severity_for_event(event: str, catalog: dict[str, Severity]) -> Severity | None:
    return catalog.get(event)


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AntiSpamPolicy(_Model):
    """Notifier-level guard on top of A5's own per-check ``IncidentPolicy.cooldown_seconds``.

    ``None`` means "no limit" for either field.
    """

    cooldown_seconds: float | None = Field(default=300, ge=0)
    rate_limit_per_hour: int | None = Field(default=20, ge=1)


DEFAULT_ANTI_SPAM_POLICY = AntiSpamPolicy()


@dataclass(frozen=True)
class AntiSpamState:
    last_sent_at: dict[str, datetime] = field(default_factory=dict)
    sent_within_hour: tuple[datetime, ...] = ()


def should_send(
    state: AntiSpamState, key: str, *, policy: AntiSpamPolicy, now: datetime
) -> tuple[AntiSpamState, bool]:
    """Total, deterministic. Suppressed sends are dropped, never queued for later."""
    last = state.last_sent_at.get(key)
    if (
        policy.cooldown_seconds is not None
        and last is not None
        and (now - last).total_seconds() < policy.cooldown_seconds
    ):
        return state, False

    window_start = now - timedelta(hours=1)
    recent = tuple(t for t in state.sent_within_hour if t > window_start)
    if policy.rate_limit_per_hour is not None and len(recent) >= policy.rate_limit_per_hour:
        return replace(state, sent_within_hour=recent), False

    new_state = AntiSpamState(
        last_sent_at={**state.last_sent_at, key: now},
        sent_within_hour=(*recent, now),
    )
    return new_state, True
