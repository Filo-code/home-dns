from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from home_dns.core.notify import (
    AlertMessage,
    AntiSpamPolicy,
    AntiSpamState,
    format_message,
    severity_for_event,
    should_send,
)

T0 = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)


def _tick(seconds: int) -> datetime:
    return T0 + timedelta(seconds=seconds)


# ------------------------------------------------------------------------------- severity routing


def test_severity_for_event_looks_up_the_catalog() -> None:
    catalog = {"storage_above_90": "critical", "storage_above_70": "warning"}
    assert severity_for_event("storage_above_90", catalog) == "critical"
    assert severity_for_event("storage_above_70", catalog) == "warning"


def test_severity_for_event_unknown_event_is_none() -> None:
    assert severity_for_event("ghost_event", {}) is None


# --------------------------------------------------------------------------------------- messages


def test_format_message_is_italian_and_includes_event_and_detail() -> None:
    text = format_message(AlertMessage("critical", "storage_above_90", "94% used"))
    assert "CRITICO" in text
    assert "storage_above_90" in text
    assert "94% used" in text


def test_format_message_severity_labels_are_distinct() -> None:
    labels = {
        format_message(AlertMessage(sev, "event", "d")).split("\n")[0]  # type: ignore[arg-type]
        for sev in ("critical", "warning", "info")
    }
    assert len(labels) == 3


# ------------------------------------------------------------------------------------- anti-spam


def test_anti_spam_policy_defaults_are_the_owner_approved_values() -> None:
    policy = AntiSpamPolicy()
    assert policy.cooldown_seconds == 300
    assert policy.rate_limit_per_hour == 20


def test_should_send_allows_the_first_message() -> None:
    state, allowed = should_send(
        AntiSpamState(), "critical:dns_down", policy=AntiSpamPolicy(), now=T0
    )
    assert allowed
    assert state.last_sent_at["critical:dns_down"] == T0


def test_should_send_suppresses_the_same_key_within_cooldown() -> None:
    policy = AntiSpamPolicy(cooldown_seconds=300, rate_limit_per_hour=None)
    state, allowed = should_send(AntiSpamState(), "k", policy=policy, now=T0)
    assert allowed

    state, allowed = should_send(state, "k", policy=policy, now=_tick(100))
    assert not allowed  # within cooldown


def test_should_send_allows_again_once_cooldown_elapses() -> None:
    policy = AntiSpamPolicy(cooldown_seconds=300, rate_limit_per_hour=None)
    state, _ = should_send(AntiSpamState(), "k", policy=policy, now=T0)
    state, allowed = should_send(state, "k", policy=policy, now=_tick(301))
    assert allowed


def test_should_send_different_keys_are_independent_of_cooldown() -> None:
    policy = AntiSpamPolicy(cooldown_seconds=300, rate_limit_per_hour=None)
    state, _ = should_send(AntiSpamState(), "a", policy=policy, now=T0)
    state, allowed = should_send(state, "b", policy=policy, now=_tick(1))
    assert allowed  # dedup is per-key


def test_should_send_zero_cooldown_never_suppresses_by_cooldown() -> None:
    policy = AntiSpamPolicy(cooldown_seconds=0, rate_limit_per_hour=None)
    state = AntiSpamState()
    for i in range(5):
        state, allowed = should_send(state, "k", policy=policy, now=_tick(i))
        assert allowed


def test_should_send_null_cooldown_means_no_limit() -> None:
    policy = AntiSpamPolicy(cooldown_seconds=None, rate_limit_per_hour=None)
    state, _ = should_send(AntiSpamState(), "k", policy=policy, now=T0)
    state, allowed = should_send(state, "k", policy=policy, now=_tick(1))
    assert allowed


def test_should_send_rate_limit_caps_total_sends_per_hour() -> None:
    policy = AntiSpamPolicy(cooldown_seconds=0, rate_limit_per_hour=3)
    state = AntiSpamState()
    results = []
    for i in range(5):
        state, allowed = should_send(state, f"key-{i}", policy=policy, now=_tick(i))
        results.append(allowed)
    assert results == [True, True, True, False, False]


def test_should_send_rate_limit_window_rolls_off_after_an_hour() -> None:
    policy = AntiSpamPolicy(cooldown_seconds=0, rate_limit_per_hour=1)
    state, allowed = should_send(AntiSpamState(), "a", policy=policy, now=T0)
    assert allowed
    state, allowed = should_send(state, "b", policy=policy, now=T0 + timedelta(minutes=30))
    assert not allowed  # still within the trailing hour

    state, allowed = should_send(state, "c", policy=policy, now=T0 + timedelta(hours=1, seconds=1))
    assert allowed  # the first send has rolled off the window


def test_should_send_null_rate_limit_means_no_limit() -> None:
    policy = AntiSpamPolicy(cooldown_seconds=0, rate_limit_per_hour=None)
    state = AntiSpamState()
    for i in range(50):
        state, allowed = should_send(state, f"key-{i}", policy=policy, now=_tick(i))
        assert allowed


@pytest.mark.parametrize(("field", "value"), [("cooldown_seconds", -1), ("rate_limit_per_hour", 0)])
def test_anti_spam_policy_rejects_invalid_values(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        AntiSpamPolicy(**{field: value})
