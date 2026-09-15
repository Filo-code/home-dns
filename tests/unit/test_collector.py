import threading
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address, IPv6Address
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from home_dns.collector import Collector, DeviceRegistry
from home_dns.core.anomaly import Anomaly, AnomalySignal
from home_dns.core.metrics import Resolution
from home_dns.core.models import DnsClient, QueryFilter, QueryOutcome, QueryPage
from home_dns.providers.base import ProviderUnavailableError
from home_dns.providers.mock import MockDnsProvider
from home_dns.storage.dashboard import DashboardStore

ROME = ZoneInfo("Europe/Rome")
T0 = datetime(2026, 9, 13, 10, 0, tzinfo=UTC)


class Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now


class FlakyProvider(MockDnsProvider):
    fail = False

    def query_log(
        self, query: QueryFilter, *, limit: int = 100, cursor: str | None = None
    ) -> QueryPage:
        if self.fail:
            raise ProviderUnavailableError("down")
        return super().query_log(query, limit=limit, cursor=cursor)


@pytest.fixture
def store(tmp_path: Path) -> DashboardStore:
    s = DashboardStore.open(tmp_path)
    yield s  # type: ignore[misc]
    s.close()


def _expected_total(provider: MockDnsProvider, since: datetime, until: datetime) -> int:
    count, cursor = 0, None
    while True:
        page = provider.query_log(QueryFilter(since=since, until=until), limit=1000, cursor=cursor)
        count += len(page.entries)
        if page.next_cursor is None:
            return count
        cursor = page.next_cursor


def _stored_total(store: DashboardStore, resolution: Resolution) -> int:
    rows = store.rollups(resolution, T0 - timedelta(days=2), T0 + timedelta(days=2))
    return sum(r[2].total for r in rows)


def test_first_poll_sets_watermark_without_backfill(store: DashboardStore) -> None:
    collector = Collector(MockDnsProvider(), store, tz=ROME, now=Clock(T0))
    assert collector.poll() == 0
    collector.flush()
    assert store.load_watermark() == T0
    assert _stored_total(store, Resolution.MINUTE) == 0


def test_poll_and_flush_store_every_query_at_every_resolution(store: DashboardStore) -> None:
    clock = Clock(T0)
    provider = MockDnsProvider(now=clock)
    collector = Collector(provider, store, tz=ROME, now=clock)
    collector.poll()
    for _ in range(5):
        clock.now += timedelta(minutes=1)
        collector.poll()
    collector.poll()  # nothing new in the same second
    collector.flush()
    expected = _expected_total(provider, T0, T0 + timedelta(minutes=5))
    assert expected > 0
    for resolution in Resolution:
        assert _stored_total(store, resolution) == expected
    assert len(store.list_devices()) == 16
    assert store.load_watermark() == T0 + timedelta(minutes=5)


def test_restart_after_unflushed_polls_loses_and_duplicates_nothing(tmp_path: Path) -> None:
    clock = Clock(T0)
    provider = MockDnsProvider(now=clock)
    store = DashboardStore.open(tmp_path)
    first = Collector(provider, store, tz=ROME, now=clock)
    first.poll()
    clock.now += timedelta(minutes=2)
    first.poll()
    first.flush()
    clock.now += timedelta(minutes=3)
    first.poll()  # polled but never flushed: simulated crash
    store.close()

    store = DashboardStore.open(tmp_path)
    second = Collector(provider, store, tz=ROME, now=clock)
    second.poll()
    second.flush()
    assert _stored_total(store, Resolution.HOUR) == _expected_total(provider, T0, clock.now)
    store.close()


def test_provider_error_keeps_watermark_and_retries_window(store: DashboardStore) -> None:
    clock = Clock(T0)
    provider = FlakyProvider(now=clock)
    collector = Collector(provider, store, tz=ROME, now=clock)
    collector.poll()
    clock.now += timedelta(minutes=3)
    provider.fail = True
    assert collector.poll() == 0
    provider.fail = False
    clock.now += timedelta(minutes=1)
    collector.poll()
    collector.flush()
    assert _stored_total(store, Resolution.MINUTE) == _expected_total(provider, T0, clock.now)


def test_rotating_ipv6_maps_to_the_same_device(store: DashboardStore) -> None:
    registry = DeviceRegistry(store)
    client = MockDnsProvider(now=lambda: T0).list_clients()[0]
    device_id = registry.observe_client(client)
    tomorrow = MockDnsProvider(now=lambda: T0 + timedelta(days=1)).list_clients()[0]
    assert tomorrow.ipv6_addresses != client.ipv6_addresses
    assert registry.observe_client(tomorrow) == device_id
    assert registry.resolve_address(str(tomorrow.ipv6_addresses[0]), T0) == device_id


def _client(mac: str | None, *addresses: str) -> DnsClient:
    v4 = tuple(IPv4Address(a) for a in addresses if ":" not in a)
    v6 = tuple(IPv6Address(a) for a in addresses if ":" in a)
    return DnsClient(
        client_id="c",
        ipv4_addresses=v4,
        ipv6_addresses=v6,
        mac=mac,
        first_seen=T0,
        last_seen=T0,
        total_queries=0,
        blocked_queries=0,
    )


def test_address_only_device_is_claimed_by_its_mac(store: DashboardStore) -> None:
    registry = DeviceRegistry(store)
    orphan = registry.resolve_address("192.0.2.50", T0)
    assert registry.observe_client(_client("00:00:5e:00:53:50", "192.0.2.50")) == orphan


def test_address_reused_by_a_different_mac_creates_a_new_device(store: DashboardStore) -> None:
    registry = DeviceRegistry(store)
    first = registry.observe_client(_client("00:00:5e:00:53:01", "192.0.2.60"))
    second = registry.observe_client(_client("00:00:5e:00:53:02", "192.0.2.60"))
    assert first != second
    assert registry.resolve_address("192.0.2.60", T0) == second


def test_registry_survives_restart(store: DashboardStore) -> None:
    clock = Clock(T0)
    collector = Collector(MockDnsProvider(now=clock), store, tz=ROME, now=clock)
    collector.poll()
    clock.now += timedelta(minutes=1)
    collector.poll()
    collector.flush()
    ids = {d.mac: d.device_id for d in store.list_devices()}
    registry = DeviceRegistry(store)
    for client in MockDnsProvider(now=clock).list_clients():
        assert registry.observe_client(client) == ids[client.mac]


def test_failed_flush_is_retried_without_losing_devices(
    store: DashboardStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock(T0)
    provider = MockDnsProvider(now=clock)
    collector = Collector(provider, store, tz=ROME, now=clock)
    collector.poll()
    clock.now += timedelta(minutes=1)
    collector.poll()
    real_flush = store.flush
    monkeypatch.setattr(store, "flush", lambda batch: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError, match="disk"):
        collector.flush()
    monkeypatch.setattr(store, "flush", real_flush)
    collector.flush()
    assert len(store.list_devices()) == 16
    assert _stored_total(store, Resolution.MINUTE) == _expected_total(provider, T0, clock.now)


def test_run_loop_flushes_on_stop(store: DashboardStore) -> None:
    clock = Clock(T0)
    collector = Collector(MockDnsProvider(now=clock), store, tz=ROME, now=clock)
    stop = threading.Event()
    stop.set()
    collector.run(stop, poll_interval=0, flush_interval=300)
    assert store.load_watermark() == T0


def test_run_loop_survives_cycle_errors(
    store: DashboardStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock(T0)
    collector = Collector(MockDnsProvider(now=clock), store, tz=ROME, now=clock)
    stop = threading.Event()
    calls = []

    def boom() -> int:
        calls.append(1)
        if len(calls) >= 2:
            stop.set()
        raise RuntimeError("bug")

    monkeypatch.setattr(collector, "poll", boom)
    collector.run(stop, poll_interval=0, flush_interval=0)
    assert len(calls) == 3  # two loop cycles + the final poll, none escaped


def test_blocked_counts_keep_their_source(store: DashboardStore) -> None:
    clock = Clock(T0)
    provider = MockDnsProvider(now=clock)
    collector = Collector(provider, store, tz=ROME, now=clock)
    collector.poll()
    clock.now += timedelta(minutes=10)
    collector.poll()
    collector.flush()
    rows = store.rollups(Resolution.DAY, T0 - timedelta(days=1), T0 + timedelta(days=1))
    blocked = sum(r[2].blocked for r in rows)
    by_source = sum(sum(r[2].blocked_by_source.values()) for r in rows)
    page = provider.query_log(
        QueryFilter(since=T0, until=clock.now, outcome=QueryOutcome.BLOCKED), limit=1000
    )
    assert blocked == by_source == len(page.entries) > 0


# ------------------------------------------------------------------------------- anomaly wiring


class _StubAnalyzer:
    """Deterministic stand-in for AnomalyAnalyzer: proves the collector wires results through to
    storage without depending on MockDnsProvider happening to generate anomalous traffic."""

    def __init__(self, result: list[Anomaly]) -> None:
        self._result = result
        self.calls = 0

    def observe(self, device_entries: object, group_of: object) -> list[Anomaly]:
        self.calls += 1
        return list(self._result)


class _BrokenAnalyzer:
    def observe(self, device_entries: object, group_of: object) -> list[Anomaly]:
        raise RuntimeError("boom")


def test_no_analyzer_means_no_anomaly_persistence(store: DashboardStore) -> None:
    clock = Clock(T0)
    provider = MockDnsProvider(now=clock)
    collector = Collector(provider, store, tz=ROME, now=clock)
    collector.poll()
    clock.now += timedelta(minutes=10)
    collector.poll()
    collector.flush()
    assert store.list_anomalies() == []


def test_analyzer_results_are_persisted_on_flush(store: DashboardStore) -> None:
    clock = Clock(T0)
    provider = MockDnsProvider(now=clock)
    canned = Anomaly(
        device_id=1,
        detected_at=T0,
        signals=(AnomalySignal.NXDOMAIN_BURST,),
        score=30,
        severity="medium",
        reason="NXDOMAIN rate significantly exceed this device's recent baseline",
    )
    analyzer = _StubAnalyzer([canned])
    collector = Collector(
        provider,
        store,
        tz=ROME,
        now=clock,
        anomaly_analyzer=analyzer,  # type: ignore[arg-type]
        anomaly_retention=timedelta(days=30),
    )
    collector.poll()
    clock.now += timedelta(minutes=10)
    collector.poll()
    assert analyzer.calls == 1  # first poll only bootstraps the watermark, reads nothing
    collector.flush()
    stored = store.list_anomalies()
    assert len(stored) == 1
    assert stored[0].signals == ("nxdomain_burst",)
    # A second poll+flush cycle with no new results must not duplicate the old one.
    clock.now += timedelta(minutes=10)
    collector.poll()
    collector.flush()
    assert len(store.list_anomalies()) == 2  # analyzer returns the same canned result each call


def test_broken_analyzer_does_not_break_the_collector(store: DashboardStore) -> None:
    clock = Clock(T0)
    provider = MockDnsProvider(now=clock)
    collector = Collector(
        provider,
        store,
        tz=ROME,
        now=clock,
        anomaly_analyzer=_BrokenAnalyzer(),  # type: ignore[arg-type]
    )
    collector.poll()
    clock.now += timedelta(minutes=10)
    read = collector.poll()  # must not raise, and metrics must still be collected
    collector.flush()
    assert read > 0
    assert store.list_anomalies() == []
    rows = store.rollups(Resolution.DAY, T0 - timedelta(days=1), T0 + timedelta(days=1))
    assert sum(r[2].total for r in rows) > 0
