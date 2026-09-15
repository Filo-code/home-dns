from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address

from home_dns.core.anomaly import (
    AnalyzerConfig,
    Anomaly,
    AnomalyAnalyzer,
    AnomalySignal,
    AnomalyThresholds,
    explain,
    looks_high_entropy,
    severity_for_score,
)
from home_dns.core.models import QueryLogEntry, QueryOutcome

FIXED_NOW = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
ADDRESS = IPv4Address("192.0.2.10")

DEFAULT_THRESHOLDS = AnomalyThresholds(
    nxdomain_burst_count=5,
    nxdomain_burst_window_minutes=5,
    query_rate_spike_multiplier=3.0,
    query_rate_baseline_minutes=5,
    beaconing_min_repeats=4,
    beaconing_interval_tolerance_seconds=2,
    entropy_threshold=3.0,
    entropy_min_label_length=8,
    failure_burst_count=5,
    failure_burst_window_minutes=5,
)


def _entry(
    id_: int,
    *,
    seconds_ago: float,
    domain: str = "example.example",
    reply_type: str | None = None,
    outcome: QueryOutcome = QueryOutcome.FORWARDED,
) -> QueryLogEntry:
    return QueryLogEntry(
        id=id_,
        time=FIXED_NOW - timedelta(seconds=seconds_ago),
        client_address=ADDRESS,
        domain=domain,
        query_type="A",
        outcome=outcome,
        reply_type=reply_type,
    )


def _analyzer(thresholds: AnomalyThresholds = DEFAULT_THRESHOLDS) -> AnomalyAnalyzer:
    config = AnalyzerConfig(
        window_minutes=30,
        max_entries_per_device=1000,
        default_group="DEFAULT",
        thresholds_by_group={"DEFAULT": thresholds},
    )
    return AnomalyAnalyzer(config, now=lambda: FIXED_NOW)


# --------------------------------------------------------------------------------- basic scoring


def test_severity_mapping() -> None:
    assert severity_for_score(0) == "low"
    assert severity_for_score(29) == "low"
    assert severity_for_score(30) == "medium"
    assert severity_for_score(59) == "medium"
    assert severity_for_score(60) == "high"
    assert severity_for_score(100) == "high"


def test_explain_is_deterministic_and_names_signals() -> None:
    text = explain((AnomalySignal.NXDOMAIN_BURST, AnomalySignal.QUERY_RATE_SPIKE))
    assert "NXDOMAIN rate" in text
    assert "query frequency" in text
    assert explain(()) == "no signals"


# ------------------------------------------------------------------------------------- entropy


def test_high_entropy_heuristic_is_deterministic() -> None:
    random_looking = "x7q9zv2mwk4t"
    word_like = "downloadserver"
    assert looks_high_entropy(f"{random_looking}.example.com", DEFAULT_THRESHOLDS) is True
    assert looks_high_entropy(f"{word_like}.example.com", DEFAULT_THRESHOLDS) is False
    # Same input, same output, every time.
    for _ in range(5):
        assert looks_high_entropy(f"{random_looking}.example.com", DEFAULT_THRESHOLDS) is True


def test_high_entropy_ignores_short_labels() -> None:
    assert looks_high_entropy("ab.example.com", DEFAULT_THRESHOLDS) is False


# --------------------------------------------------------------------------------- normal traffic


def test_normal_traffic_does_not_trigger() -> None:
    analyzer = _analyzer()
    entries = [
        (1, _entry(i, seconds_ago=i * 10, domain=f"site{i}.example.com")) for i in range(1, 6)
    ]
    result = analyzer.observe(entries, {1: "DEFAULT"})
    assert result == []


# ------------------------------------------------------------------------------- NXDOMAIN burst


def test_nxdomain_burst_triggers() -> None:
    analyzer = _analyzer()
    entries = [
        (1, _entry(i, seconds_ago=i * 10, domain=f"bad{i}.invalid", reply_type="NXDOMAIN"))
        for i in range(1, 7)  # 6 >= threshold of 5
    ]
    result = analyzer.observe(entries, {1: "DEFAULT"})
    assert len(result) == 1
    assert AnomalySignal.NXDOMAIN_BURST in result[0].signals


def test_nxdomain_below_threshold_does_not_trigger() -> None:
    analyzer = _analyzer()
    entries = [
        (1, _entry(i, seconds_ago=i * 10, domain=f"bad{i}.invalid", reply_type="NXDOMAIN"))
        for i in range(1, 4)  # 3 < threshold of 5
    ]
    assert analyzer.observe(entries, {1: "DEFAULT"}) == []


# --------------------------------------------------------------------------- query-rate spike


def test_query_rate_spike_triggers() -> None:
    analyzer = _analyzer()
    # Older baseline window (5-10 min ago): 2 queries. Recent window (0-5 min ago): 8 queries.
    # 8 >= 2 * 3.0 -> spike.
    older = [
        (1, _entry(i, seconds_ago=300 + i * 30, domain=f"old{i}.example.com")) for i in range(1, 3)
    ]
    recent = [
        (1, _entry(100 + i, seconds_ago=i * 20, domain=f"new{i}.example.com")) for i in range(1, 9)
    ]
    result = analyzer.observe(older + recent, {1: "DEFAULT"})
    assert len(result) == 1
    assert AnomalySignal.QUERY_RATE_SPIKE in result[0].signals


def test_query_rate_spike_needs_a_baseline() -> None:
    analyzer = _analyzer()
    # Only recent queries, no older baseline -> never flagged as a spike (nothing to compare to).
    entries = [(1, _entry(i, seconds_ago=i * 5, domain=f"n{i}.example.com")) for i in range(1, 9)]
    result = analyzer.observe(entries, {1: "DEFAULT"})
    assert not any(AnomalySignal.QUERY_RATE_SPIKE in a.signals for a in result)


# ------------------------------------------------------------------------------------ beaconing


def test_repeated_domain_beaconing_triggers() -> None:
    analyzer = _analyzer()
    # Same domain, 5 queries at a very regular ~60s interval.
    entries = [(1, _entry(i, seconds_ago=(5 - i) * 60, domain="c2.example.net")) for i in range(5)]
    result = analyzer.observe(entries, {1: "DEFAULT"})
    assert len(result) == 1
    assert AnomalySignal.BEACONING in result[0].signals


def test_irregular_repeats_do_not_trigger_beaconing() -> None:
    analyzer = _analyzer()
    # Same domain, but wildly irregular intervals.
    offsets = [500, 480, 300, 250, 40]
    entries = [
        (1, _entry(i, seconds_ago=offset, domain="chatty.example.net"))
        for i, offset in enumerate(offsets)
    ]
    result = analyzer.observe(entries, {1: "DEFAULT"})
    assert not any(AnomalySignal.BEACONING in a.signals for a in result)


# ------------------------------------------------------------------------------ repeated failures


def test_repeated_failures_trigger() -> None:
    analyzer = _analyzer()
    entries = [
        (1, _entry(i, seconds_ago=i * 10, domain=f"broken{i}.example.com", reply_type="SERVFAIL"))
        for i in range(1, 7)
    ]
    result = analyzer.observe(entries, {1: "DEFAULT"})
    assert len(result) == 1
    assert AnomalySignal.REPEATED_FAILURES in result[0].signals


# ------------------------------------------------------------------------------- combined signals


def test_multiple_signals_combine_into_one_higher_score() -> None:
    analyzer = _analyzer()
    nx = [
        (1, _entry(i, seconds_ago=i * 5, domain=f"bad{i}.invalid", reply_type="NXDOMAIN"))
        for i in range(1, 7)
    ]
    beacon = [
        (1, _entry(100 + i, seconds_ago=(5 - i) * 60, domain="c2.example.net")) for i in range(5)
    ]
    result = analyzer.observe(nx + beacon, {1: "DEFAULT"})
    assert len(result) == 1
    anomaly = result[0]
    assert AnomalySignal.NXDOMAIN_BURST in anomaly.signals
    assert AnomalySignal.BEACONING in anomaly.signals
    assert anomaly.score > max(30, 20)  # strictly more than either signal alone would score
    assert anomaly.severity in ("medium", "high")


# ------------------------------------------------------------------------- device-group thresholds


def test_device_group_thresholds_are_respected() -> None:
    permissive = AnomalyThresholds(
        nxdomain_burst_count=100,  # unreachable in this test -> group never fires
        nxdomain_burst_window_minutes=5,
        query_rate_spike_multiplier=3.0,
        query_rate_baseline_minutes=5,
        beaconing_min_repeats=4,
        beaconing_interval_tolerance_seconds=2,
        entropy_threshold=3.0,
        entropy_min_label_length=8,
        failure_burst_count=5,
        failure_burst_window_minutes=5,
    )
    config = AnalyzerConfig(
        window_minutes=30,
        max_entries_per_device=1000,
        default_group="DEFAULT",
        thresholds_by_group={"DEFAULT": DEFAULT_THRESHOLDS, "SMART-TV": permissive},
    )
    entries = [
        (1, _entry(i, seconds_ago=i * 10, domain=f"bad{i}.invalid", reply_type="NXDOMAIN"))
        for i in range(1, 7)
    ]

    default_analyzer = AnomalyAnalyzer(config, now=lambda: FIXED_NOW)
    assert default_analyzer.observe(entries, {1: "DEFAULT"}) != []

    tv_analyzer = AnomalyAnalyzer(config, now=lambda: FIXED_NOW)
    assert tv_analyzer.observe(entries, {1: "SMART-TV"}) == []


def test_unknown_group_falls_back_to_default_thresholds() -> None:
    analyzer = _analyzer()
    entries = [
        (1, _entry(i, seconds_ago=i * 10, domain=f"bad{i}.invalid", reply_type="NXDOMAIN"))
        for i in range(1, 7)
    ]
    result = analyzer.observe(entries, {1: "SOME-UNCONFIGURED-GROUP"})
    assert len(result) == 1


# --------------------------------------------------------------------------------- robustness


def test_malformed_group_mapping_does_not_crash_the_analyzer() -> None:
    analyzer = _analyzer()
    entries = [(1, _entry(1, seconds_ago=1))]
    # group_of has no entry for device 1 at all -> falls back to default_group, no crash.
    assert analyzer.observe(entries, {}) == []


def test_empty_batch_returns_no_anomalies() -> None:
    analyzer = _analyzer()
    assert analyzer.observe([], {}) == []


def test_anomaly_is_a_plain_frozen_dataclass() -> None:
    anomaly = Anomaly(
        device_id=1,
        detected_at=FIXED_NOW,
        signals=(AnomalySignal.NXDOMAIN_BURST,),
        score=30,
        severity="medium",
        reason="NXDOMAIN rate significantly exceed this device's recent baseline",
    )
    assert anomaly.device_id == 1
    assert anomaly.severity == "medium"
