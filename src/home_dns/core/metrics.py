"""Mergeable DNS metrics: rollups, latency histograms and bucket boundaries.

Pure, no I/O. See docs/specs/a7-backend.md §5. Histograms merge by addition, so minute rollups
combine into hour and day rollups without keeping individual samples; the price is that
percentiles are exact only to the histogram bin.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from home_dns.core.models import QueryLogEntry, QueryOutcome

# Upper bounds in milliseconds; one extra overflow bin collects everything above the last one.
LATENCY_BINS_MS: tuple[float, ...] = (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000)


class Resolution(StrEnum):
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"


def _empty_histogram() -> list[int]:
    return [0] * (len(LATENCY_BINS_MS) + 1)


@dataclass
class Rollup:
    total: int = 0
    blocked: int = 0
    cached: int = 0
    forwarded: int = 0
    latency_histogram: list[int] = field(default_factory=_empty_histogram)
    blocked_by_source: dict[str, int] = field(default_factory=dict)

    def add(self, entry: QueryLogEntry) -> None:
        self.total += 1
        if entry.outcome is QueryOutcome.BLOCKED:
            self.blocked += 1
            source = entry.blocked_by or "unknown"
            self.blocked_by_source[source] = self.blocked_by_source.get(source, 0) + 1
        elif entry.outcome is QueryOutcome.CACHED:
            self.cached += 1
        elif entry.outcome is QueryOutcome.FORWARDED:
            self.forwarded += 1
        if entry.latency_ms is not None:
            self.latency_histogram[_bin_index(entry.latency_ms)] += 1

    def merge(self, other: Rollup) -> None:
        self.total += other.total
        self.blocked += other.blocked
        self.cached += other.cached
        self.forwarded += other.forwarded
        self.latency_histogram = [
            a + b for a, b in zip(self.latency_histogram, other.latency_histogram, strict=True)
        ]
        for source, count in other.blocked_by_source.items():
            self.blocked_by_source[source] = self.blocked_by_source.get(source, 0) + count

    @property
    def block_percentage(self) -> float:
        return round(100 * self.blocked / self.total, 2) if self.total else 0.0

    @property
    def cache_hit_ratio(self) -> float | None:
        """Blocked queries never reach cache or upstream, so they are excluded."""
        answered = self.cached + self.forwarded
        return round(self.cached / answered, 4) if answered else None

    def latency_percentile(self, percentile: float) -> float | None:
        """Upper bound of the bin holding the percentile; the overflow bin reports the last
        finite bound (a lower bound, not the true value). None without samples."""
        if not 0 < percentile <= 100:
            raise ValueError("percentile must be in (0, 100]")
        samples = sum(self.latency_histogram)
        if samples == 0:
            return None
        rank = percentile / 100 * samples
        running = 0
        for index, count in enumerate(self.latency_histogram):
            running += count
            if running >= rank:
                return LATENCY_BINS_MS[min(index, len(LATENCY_BINS_MS) - 1)]
        return LATENCY_BINS_MS[-1]  # pragma: no cover - rank <= samples always returns above


def _bin_index(latency_ms: float) -> int:
    for index, bound in enumerate(LATENCY_BINS_MS):
        if latency_ms <= bound:
            return index
    return len(LATENCY_BINS_MS)


def bucket_start(moment: datetime, resolution: Resolution, tz: ZoneInfo) -> datetime:
    """Minute and hour buckets are UTC; day buckets start at local midnight in ``tz``."""
    utc = moment.astimezone(UTC)
    if resolution is Resolution.MINUTE:
        return utc.replace(second=0, microsecond=0)
    if resolution is Resolution.HOUR:
        return utc.replace(minute=0, second=0, microsecond=0)
    local = utc.astimezone(tz)
    return datetime(local.year, local.month, local.day, tzinfo=tz).astimezone(UTC)


def bucket_end(start: datetime, resolution: Resolution, tz: ZoneInfo) -> datetime:
    if resolution is Resolution.MINUTE:
        return start + timedelta(minutes=1)
    if resolution is Resolution.HOUR:
        return start + timedelta(hours=1)
    local_date = start.astimezone(tz).date() + timedelta(days=1)
    return datetime(local_date.year, local_date.month, local_date.day, tzinfo=tz).astimezone(UTC)
