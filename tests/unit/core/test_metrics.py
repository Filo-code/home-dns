from datetime import UTC, datetime
from ipaddress import IPv4Address
from zoneinfo import ZoneInfo

import pytest

from home_dns.core.metrics import LATENCY_BINS_MS, Resolution, Rollup, bucket_end, bucket_start
from home_dns.core.models import QueryLogEntry, QueryOutcome

ROME = ZoneInfo("Europe/Rome")


def _entry(
    outcome: QueryOutcome, latency: float | None = 3.0, source: str | None = None
) -> QueryLogEntry:
    return QueryLogEntry(
        id=1,
        time=datetime(2026, 9, 13, tzinfo=UTC),
        client_address=IPv4Address("192.0.2.10"),
        domain="a.example",
        query_type="A",
        outcome=outcome,
        blocked_by=source,
        latency_ms=latency,
    )


def test_add_counts_outcomes_sources_and_latency() -> None:
    rollup = Rollup()
    rollup.add(_entry(QueryOutcome.BLOCKED, 0.1, "list-a"))
    rollup.add(_entry(QueryOutcome.BLOCKED, 0.1))
    rollup.add(_entry(QueryOutcome.CACHED, 0.5))
    rollup.add(_entry(QueryOutcome.FORWARDED, 30))
    rollup.add(_entry(QueryOutcome.OTHER, None))
    assert (rollup.total, rollup.blocked, rollup.cached, rollup.forwarded) == (5, 2, 1, 1)
    assert rollup.blocked_by_source == {"list-a": 1, "unknown": 1}
    assert sum(rollup.latency_histogram) == 4
    assert rollup.block_percentage == 40.0
    assert rollup.cache_hit_ratio == 0.5


def test_merge_equals_adding_everything_to_one_rollup() -> None:
    entries = [_entry(QueryOutcome.FORWARDED, ms) for ms in (0.5, 4, 40, 400, 4000)]
    entries.append(_entry(QueryOutcome.BLOCKED, 0.2, "list-a"))
    whole = Rollup()
    for e in entries:
        whole.add(e)
    left, right = Rollup(), Rollup()
    for e in entries[:3]:
        left.add(e)
    for e in entries[3:]:
        right.add(e)
    left.merge(right)
    assert left == whole


def test_empty_rollup_has_no_ratios() -> None:
    assert Rollup().block_percentage == 0.0
    assert Rollup().cache_hit_ratio is None
    assert Rollup().latency_percentile(50) is None


def test_percentiles_report_bin_upper_bounds() -> None:
    rollup = Rollup()
    for ms in [0.5] * 50 + [15] * 45 + [150] * 5:
        rollup.add(_entry(QueryOutcome.FORWARDED, ms))
    assert rollup.latency_percentile(50) == 1
    assert rollup.latency_percentile(95) == 20
    assert rollup.latency_percentile(100) == 200


def test_overflow_bin_reports_last_finite_bound() -> None:
    rollup = Rollup()
    rollup.add(_entry(QueryOutcome.FORWARDED, 99999))
    assert rollup.latency_percentile(50) == LATENCY_BINS_MS[-1]


@pytest.mark.parametrize("bad", [0, -1, 101])
def test_percentile_range_is_validated(bad: float) -> None:
    with pytest.raises(ValueError, match="percentile"):
        Rollup().latency_percentile(bad)


def test_minute_and_hour_buckets_are_utc() -> None:
    moment = datetime(2026, 9, 13, 10, 42, 17, 5, tzinfo=UTC)
    assert bucket_start(moment, Resolution.MINUTE, ROME) == datetime(
        2026, 9, 13, 10, 42, tzinfo=UTC
    )
    assert bucket_start(moment, Resolution.HOUR, ROME) == datetime(2026, 9, 13, 10, tzinfo=UTC)
    start = bucket_start(moment, Resolution.HOUR, ROME)
    assert bucket_end(start, Resolution.HOUR, ROME) == datetime(2026, 9, 13, 11, tzinfo=UTC)
    start = bucket_start(moment, Resolution.MINUTE, ROME)
    assert bucket_end(start, Resolution.MINUTE, ROME) == datetime(2026, 9, 13, 10, 43, tzinfo=UTC)


def test_day_bucket_starts_at_local_midnight() -> None:
    # 23:30 UTC on 12 Sep is already 13 Sep in Rome (UTC+2 in summer).
    start = bucket_start(datetime(2026, 9, 12, 23, 30, tzinfo=UTC), Resolution.DAY, ROME)
    assert start == datetime(2026, 9, 12, 22, tzinfo=UTC)
    assert bucket_end(start, Resolution.DAY, ROME) == datetime(2026, 9, 13, 22, tzinfo=UTC)


@pytest.mark.parametrize(
    ("day", "hours"),
    [(datetime(2026, 3, 29, 12, tzinfo=UTC), 23), (datetime(2026, 10, 25, 12, tzinfo=UTC), 25)],
)
def test_dst_days_are_23_or_25_hours(day: datetime, hours: int) -> None:
    start = bucket_start(day, Resolution.DAY, ROME)
    assert (bucket_end(start, Resolution.DAY, ROME) - start).total_seconds() == hours * 3600
