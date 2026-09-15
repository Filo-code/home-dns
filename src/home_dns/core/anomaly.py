"""Passive, deterministic, non-ML DNS anomaly detection.

Design (see docs/anomaly-detection/architecture.md and docs/anomaly-detection/signals.md):

* Runs entirely downstream of already-answered DNS queries. Never in the DNS critical path,
  never decides whether a query is allowed or blocked, never touches Pi-hole configuration.
* Stateful only in RAM, per device, in a small bounded window (``AnalyzerConfig.window_minutes``
  / ``max_entries_per_device``). Raw per-query domain data is never written to disk — only the
  small, derived ``Anomaly`` events (signal names + a score + a short explanation) are meant to
  be persisted, by the caller, via the existing storage layer.
* Every threshold is configuration, not a hard-coded constant — see ``AnomalyThresholds``.
* The combined score is a simple, named, additive sum of triggered-signal weights — explicitly
  not a probability and not a machine-learning output.
* ``looks_high_entropy`` is a heuristic only. It flags domains that *look* like random tokens;
  it does not identify malware, DGA activity, or any threat with certainty, and it will both
  miss real threats and flag legitimate randomly-named infrastructure (CDN hashes, tracking
  pixels). It is one input among several, never a standalone verdict.
"""

from __future__ import annotations

import logging
import math
from collections import Counter, deque
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from itertools import pairwise
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from home_dns.core.models import QueryLogEntry

logger = logging.getLogger(__name__)

AnomalySeverity = Literal["low", "medium", "high"]

# Failure-ish reply kinds Pi-hole reports; SERVFAIL/REFUSED/NOTIMP are genuine resolution
# failures, distinct from a normal NXDOMAIN (a valid "does not exist" answer).
_FAILURE_REPLY_TYPES = frozenset({"SERVFAIL", "REFUSED", "NOTIMP"})
_NXDOMAIN_REPLY_TYPE = "NXDOMAIN"


class AnomalySignal(StrEnum):
    NXDOMAIN_BURST = "nxdomain_burst"
    QUERY_RATE_SPIKE = "query_rate_spike"
    BEACONING = "beaconing"
    HIGH_ENTROPY_DOMAIN = "high_entropy_domain"
    REPEATED_FAILURES = "repeated_failures"


# Fixed, documented weights — not configurable per-group (the *thresholds* that decide whether
# a signal fires at all are configurable; once it fires, its contribution to the score is fixed
# so the score stays comparable and explainable across devices).
SIGNAL_WEIGHT: dict[AnomalySignal, int] = {
    AnomalySignal.NXDOMAIN_BURST: 30,
    AnomalySignal.QUERY_RATE_SPIKE: 25,
    AnomalySignal.BEACONING: 20,
    AnomalySignal.HIGH_ENTROPY_DOMAIN: 15,
    AnomalySignal.REPEATED_FAILURES: 30,
}

_SIGNAL_LABEL: dict[AnomalySignal, str] = {
    AnomalySignal.NXDOMAIN_BURST: "NXDOMAIN rate",
    AnomalySignal.QUERY_RATE_SPIKE: "query frequency",
    AnomalySignal.BEACONING: "regular repeated-domain interval",
    AnomalySignal.HIGH_ENTROPY_DOMAIN: "random-looking domain names",
    AnomalySignal.REPEATED_FAILURES: "resolution failure rate",
}


def severity_for_score(score: int) -> AnomalySeverity:
    if score >= 60:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


def explain(signals: tuple[AnomalySignal, ...]) -> str:
    """A short, deterministic, human-readable sentence — never a claim of certainty."""
    if not signals:
        return "no signals"
    labels = [_SIGNAL_LABEL[s] for s in signals]
    joined = labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + f" and {labels[-1]}"
    return f"{joined} significantly exceed this device's recent baseline"


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AnomalyThresholds(_Model):
    """One device-group's tuning knobs. Every number here is configuration — see
    config/anomaly-detection/anomaly-detection.yaml — never hard-coded per call site."""

    nxdomain_burst_count: int = Field(ge=1)
    nxdomain_burst_window_minutes: int = Field(ge=1)
    query_rate_spike_multiplier: float = Field(gt=1)
    query_rate_baseline_minutes: int = Field(ge=1)
    beaconing_min_repeats: int = Field(ge=3)
    beaconing_interval_tolerance_seconds: float = Field(ge=0)
    entropy_threshold: float = Field(ge=0)
    entropy_min_label_length: int = Field(ge=1)
    failure_burst_count: int = Field(ge=1)
    failure_burst_window_minutes: int = Field(ge=1)


@dataclass(frozen=True)
class Anomaly:
    device_id: int
    detected_at: datetime
    signals: tuple[AnomalySignal, ...]
    score: int
    severity: AnomalySeverity
    reason: str


def _entropy_bits_per_char(label: str) -> float:
    """Shannon entropy of the label's character distribution. Pure function, no external data."""
    if not label:
        return 0.0
    counts = Counter(label)
    length = len(label)
    return -sum((n / length) * math.log2(n / length) for n in counts.values())


def looks_high_entropy(domain: str, thresholds: AnomalyThresholds) -> bool:
    """See the module docstring: a heuristic, not a detector of malware/DGA with certainty."""
    label = domain.split(".")[0]
    if len(label) < thresholds.entropy_min_label_length:
        return False
    lowered = label.lower()
    letters = [c for c in lowered if c.isalpha()]
    vowels = sum(c in "aeiou" for c in letters)
    vowel_ratio = vowels / len(letters) if letters else 0.0
    entropy = _entropy_bits_per_char(lowered)
    # High entropy plus a low vowel ratio reads more like a random token than an ordinary
    # word-based subdomain; entropy alone over-fires on legitimate hash-like CDN hostnames.
    return entropy >= thresholds.entropy_threshold and vowel_ratio < 0.3


@dataclass
class _DeviceWindow:
    """In-memory only, bounded, never persisted. ``entries`` holds (time, domain, reply_type)
    for beaconing/entropy/failure/NXDOMAIN signals."""

    entries: deque[tuple[datetime, str, str | None]] = field(default_factory=deque)


@dataclass(frozen=True)
class AnalyzerConfig:
    window_minutes: int
    max_entries_per_device: int
    default_group: str
    thresholds_by_group: Mapping[str, AnomalyThresholds]

    def thresholds_for(self, group_id: str) -> AnomalyThresholds:
        return self.thresholds_by_group.get(group_id, self.thresholds_by_group[self.default_group])


class AnomalyAnalyzer:
    """Stateful, in-process, in-memory only. Feed it the (device_id, QueryLogEntry) pairs a
    collector already resolved — this makes no provider calls of its own and adds nothing to
    the DNS critical path. ``observe`` never raises: malformed input is skipped, not fatal,
    since a bug here must never take down metrics collection (design goal #1/#2)."""

    def __init__(
        self, config: AnalyzerConfig, *, now: Callable[[], datetime] | None = None
    ) -> None:
        self._config = config
        self._now = now or (lambda: datetime.now(UTC))
        self._windows: dict[int, _DeviceWindow] = {}

    def observe(
        self, device_entries: Iterable[tuple[int, QueryLogEntry]], group_of: Mapping[int, str]
    ) -> list[Anomaly]:
        anomalies: list[Anomaly] = []
        touched: set[int] = set()
        for device_id, entry in device_entries:
            try:
                self._record(device_id, entry)
                touched.add(device_id)
            except Exception:
                logger.warning("anomaly analyzer: skipped a malformed entry (device %s)", device_id)
        for device_id in touched:
            try:
                group_id = group_of.get(device_id, self._config.default_group)
                result = self._evaluate(device_id, group_id)
            except Exception:
                logger.warning("anomaly analyzer: evaluation failed for device %s", device_id)
                continue
            if result is not None:
                anomalies.append(result)
        return anomalies

    def _record(self, device_id: int, entry: QueryLogEntry) -> None:
        window = self._windows.setdefault(device_id, _DeviceWindow())
        window.entries.append((entry.time, entry.domain, entry.reply_type))
        cutoff = self._now() - timedelta(minutes=self._config.window_minutes)
        while window.entries and window.entries[0][0] < cutoff:
            window.entries.popleft()
        while len(window.entries) > self._config.max_entries_per_device:
            window.entries.popleft()

    def _evaluate(self, device_id: int, group_id: str) -> Anomaly | None:
        window = self._windows.get(device_id)
        if window is None or not window.entries:
            return None
        thresholds = self._config.thresholds_for(group_id)
        now = self._now()
        signals: list[AnomalySignal] = []

        if _nxdomain_burst(window, thresholds, now):
            signals.append(AnomalySignal.NXDOMAIN_BURST)
        if _query_rate_spike(window, thresholds, now):
            signals.append(AnomalySignal.QUERY_RATE_SPIKE)
        if _beaconing(window, thresholds):
            signals.append(AnomalySignal.BEACONING)
        if _high_entropy_present(window, thresholds):
            signals.append(AnomalySignal.HIGH_ENTROPY_DOMAIN)
        if _repeated_failures(window, thresholds, now):
            signals.append(AnomalySignal.REPEATED_FAILURES)

        if not signals:
            return None
        ordered = tuple(signals)
        score = min(sum(SIGNAL_WEIGHT[s] for s in ordered), 100)
        return Anomaly(
            device_id=device_id,
            detected_at=now,
            signals=ordered,
            score=score,
            severity=severity_for_score(score),
            reason=explain(ordered),
        )


def _nxdomain_burst(window: _DeviceWindow, thresholds: AnomalyThresholds, now: datetime) -> bool:
    cutoff = now - timedelta(minutes=thresholds.nxdomain_burst_window_minutes)
    count = sum(1 for t, _, r in window.entries if t >= cutoff and r == _NXDOMAIN_REPLY_TYPE)
    return count >= thresholds.nxdomain_burst_count


def _repeated_failures(window: _DeviceWindow, thresholds: AnomalyThresholds, now: datetime) -> bool:
    cutoff = now - timedelta(minutes=thresholds.failure_burst_window_minutes)
    count = sum(1 for t, _, r in window.entries if t >= cutoff and r in _FAILURE_REPLY_TYPES)
    return count >= thresholds.failure_burst_count


def _query_rate_spike(window: _DeviceWindow, thresholds: AnomalyThresholds, now: datetime) -> bool:
    baseline_span = timedelta(minutes=thresholds.query_rate_baseline_minutes)
    recent_cutoff = now - baseline_span
    older_cutoff = recent_cutoff - baseline_span
    recent = sum(1 for t, _, _ in window.entries if t >= recent_cutoff)
    older = sum(1 for t, _, _ in window.entries if older_cutoff <= t < recent_cutoff)
    if older == 0:
        return False  # no baseline yet: never flag a spike against nothing
    return recent >= older * thresholds.query_rate_spike_multiplier


def _beaconing(window: _DeviceWindow, thresholds: AnomalyThresholds) -> bool:
    by_domain: dict[str, list[datetime]] = {}
    for t, domain, _ in window.entries:
        by_domain.setdefault(domain, []).append(t)
    for times in by_domain.values():
        if len(times) < thresholds.beaconing_min_repeats:
            continue
        times.sort()
        intervals = [(b - a).total_seconds() for a, b in pairwise(times)]
        if not intervals:
            continue
        mean_interval = sum(intervals) / len(intervals)
        if mean_interval <= 0:
            continue
        deviation = max(abs(i - mean_interval) for i in intervals)
        if deviation <= thresholds.beaconing_interval_tolerance_seconds:
            return True
    return False


def _high_entropy_present(window: _DeviceWindow, thresholds: AnomalyThresholds) -> bool:
    return any(looks_high_entropy(domain, thresholds) for _, domain, _ in window.entries)
