from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from home_dns.core.monitoring import (
    BackoffPolicy,
    CheckResult,
    CheckStatus,
    FreshnessCounter,
    Incident,
    IncidentPolicy,
    IncidentState,
    TransitionKind,
    advance_freshness,
    advance_incident,
    advance_restart_budget,
    freshness_severity,
    reset_restart_budget,
)

T0 = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)


def _tick(n: int) -> datetime:
    return T0 + timedelta(minutes=n)


def _ok(name: str = "storage") -> CheckResult:
    return CheckResult(name, CheckStatus.OK)


def _problem(name: str = "storage") -> CheckResult:
    return CheckResult(name, CheckStatus.PROBLEM, "bad")


# --------------------------------------------------------------------------------- state machine


def test_single_bad_result_is_suspect_not_incident() -> None:
    policy = IncidentPolicy(incident_after=2)
    incident, transition = advance_incident(
        Incident("storage"), _problem(), policy=policy, now=_tick(0)
    )
    assert incident.state is IncidentState.SUSPECT
    assert transition is TransitionKind.NONE


def test_second_consecutive_bad_result_opens_incident_exactly_once() -> None:
    policy = IncidentPolicy(incident_after=2)
    suspect, _ = advance_incident(Incident("storage"), _problem(), policy=policy, now=_tick(0))
    incident, transition = advance_incident(suspect, _problem(), policy=policy, now=_tick(1))
    assert incident.state is IncidentState.INCIDENT
    assert transition is TransitionKind.OPENED
    assert incident.opened_at == _tick(1)


def test_flapping_single_bad_then_good_reverts_silently() -> None:
    """A simulated flapping input: bad, good, bad, good... never opens an incident."""
    policy = IncidentPolicy(incident_after=2)
    incident = Incident("storage")
    for minute in range(10):
        result = _problem() if minute % 2 == 0 else _ok()
        incident, transition = advance_incident(incident, result, policy=policy, now=_tick(minute))
        assert transition is TransitionKind.NONE
        assert incident.state in (IncidentState.OK, IncidentState.SUSPECT)


def test_long_outage_produces_exactly_one_alert_then_one_recovery() -> None:
    policy = IncidentPolicy(incident_after=2, recovered_after=1)
    incident = Incident("storage")
    transitions = []
    for minute in range(20):
        incident, transition = advance_incident(
            incident, _problem(), policy=policy, now=_tick(minute)
        )
        transitions.append(transition)
    assert transitions.count(TransitionKind.OPENED) == 1
    assert transitions.count(TransitionKind.RECOVERED) == 0

    incident, transition = advance_incident(incident, _ok(), policy=policy, now=_tick(20))
    assert transition is TransitionKind.RECOVERED
    assert incident.state is IncidentState.OK


def test_recovery_needs_recovered_after_consecutive_ok_results() -> None:
    policy = IncidentPolicy(incident_after=1, recovered_after=2)
    incident, _ = advance_incident(Incident("storage"), _problem(), policy=policy, now=_tick(0))
    assert incident.state is IncidentState.INCIDENT

    incident, transition = advance_incident(incident, _ok(), policy=policy, now=_tick(1))
    assert incident.state is IncidentState.RECOVERING
    assert transition is TransitionKind.NONE

    incident, transition = advance_incident(incident, _ok(), policy=policy, now=_tick(2))
    assert incident.state is IncidentState.OK
    assert transition is TransitionKind.RECOVERED


def test_relapse_during_recovering_goes_straight_back_to_incident_no_new_alert() -> None:
    policy = IncidentPolicy(incident_after=1, recovered_after=2)
    incident, _ = advance_incident(Incident("storage"), _problem(), policy=policy, now=_tick(0))
    incident, _ = advance_incident(incident, _ok(), policy=policy, now=_tick(1))
    assert incident.state is IncidentState.RECOVERING

    incident, transition = advance_incident(incident, _problem(), policy=policy, now=_tick(2))
    assert incident.state is IncidentState.INCIDENT
    assert transition is TransitionKind.NONE  # no re-suspect, no duplicate alert


def test_reminder_fires_once_cooldown_elapses_then_resets_the_clock() -> None:
    policy = IncidentPolicy(incident_after=1, cooldown_seconds=60)
    incident, transition = advance_incident(
        Incident("storage"), _problem(), policy=policy, now=_tick(0)
    )
    assert transition is TransitionKind.OPENED

    # 30s later: not due yet
    soon = _tick(0) + timedelta(seconds=30)
    incident, transition = advance_incident(incident, _problem(), policy=policy, now=soon)
    assert transition is TransitionKind.NONE

    # 90s after open: cooldown elapsed
    later = _tick(0) + timedelta(seconds=90)
    incident, transition = advance_incident(incident, _problem(), policy=policy, now=later)
    assert transition is TransitionKind.REMINDER
    assert incident.last_notified_at == later


def test_zero_cooldown_never_reminds() -> None:
    policy = IncidentPolicy(incident_after=1, cooldown_seconds=0)
    incident, _ = advance_incident(Incident("storage"), _problem(), policy=policy, now=_tick(0))
    for minute in range(1, 100):
        incident, transition = advance_incident(
            incident, _problem(), policy=policy, now=_tick(minute)
        )
        assert transition is TransitionKind.NONE


def test_advance_incident_rejects_check_name_mismatch() -> None:
    with pytest.raises(ValueError, match="check name mismatch"):
        advance_incident(
            Incident("storage"),
            CheckResult("other", CheckStatus.OK),
            policy=IncidentPolicy(),
            now=_tick(0),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [("incident_after", 0), ("recovered_after", 0), ("cooldown_seconds", -1)],
)
def test_incident_policy_rejects_invalid_values(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        IncidentPolicy(**{field: value})


# ----------------------------------------------------------------------------------- restart budget


def test_restart_budget_backs_off_exponentially_up_to_the_cap() -> None:
    policy = BackoffPolicy(
        max_attempts=10, base_delay_seconds=1.0, max_delay_seconds=5.0, backoff_factor=2.0
    )
    budget = reset_restart_budget()
    delays = []
    for _ in range(4):
        budget, delay = advance_restart_budget(budget, policy=policy)
        delays.append(delay)
    assert delays == [1.0, 2.0, 4.0, 5.0]  # capped at max_delay_seconds
    assert not budget.exhausted


def test_restart_budget_exhausts_and_stops_restarting_not_infinitely() -> None:
    policy = BackoffPolicy(max_attempts=3)
    budget = reset_restart_budget()
    for _ in range(2):
        budget, delay = advance_restart_budget(budget, policy=policy)
        assert delay is not None
        assert not budget.exhausted
    budget, delay = advance_restart_budget(budget, policy=policy)
    assert delay is None
    assert budget.exhausted

    # Further calls stay exhausted forever — never resumes retrying on its own.
    for _ in range(5):
        budget, delay = advance_restart_budget(budget, policy=policy)
        assert delay is None
        assert budget.exhausted


def test_reset_restart_budget_clears_exhaustion() -> None:
    policy = BackoffPolicy(max_attempts=1)
    budget, delay = advance_restart_budget(reset_restart_budget(), policy=policy)
    assert budget.exhausted and delay is None
    fresh = reset_restart_budget()
    assert fresh.attempts == 0 and not fresh.exhausted


@pytest.mark.parametrize(
    ("field", "value"),
    [("max_attempts", 0), ("base_delay_seconds", 0), ("backoff_factor", 0.5)],
)
def test_backoff_policy_rejects_invalid_values(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        BackoffPolicy(**{field: value})


def test_backoff_policy_rejects_max_delay_below_base_delay() -> None:
    with pytest.raises(ValidationError, match="max_delay_seconds"):
        BackoffPolicy(base_delay_seconds=10, max_delay_seconds=5)


# --------------------------------------------------------------------------- freshness escalation


def test_freshness_escalation_ladder_warning_warning_critical_then_reset() -> None:
    counter = FreshnessCounter("list-a")
    counter = advance_freshness(counter, kept_previous=True)
    assert freshness_severity(counter.consecutive_kept_previous) == "warning"  # 1st

    counter = advance_freshness(counter, kept_previous=True)
    assert freshness_severity(counter.consecutive_kept_previous) == "warning"  # 2nd

    counter = advance_freshness(counter, kept_previous=True)
    assert freshness_severity(counter.consecutive_kept_previous) == "critical"  # 3rd

    counter = advance_freshness(counter, kept_previous=True)
    assert freshness_severity(counter.consecutive_kept_previous) == "critical"  # stays critical

    counter = advance_freshness(counter, kept_previous=False)  # activated or unchanged
    assert counter.consecutive_kept_previous == 0
    assert freshness_severity(counter.consecutive_kept_previous) is None


def test_freshness_severity_is_none_at_zero() -> None:
    assert freshness_severity(0) is None
