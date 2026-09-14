from datetime import UTC, datetime
from ipaddress import IPv4Network, IPv6Network

from home_dns.core.models import HealthStatus
from home_dns.providers.mock import SAMPLE_DEVICE_NAMES, MockDnsProvider

FIXED_NOW = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
DOC_V4 = IPv4Network("192.0.2.0/24")
DOC_V6 = IPv6Network("2001:db8::/32")


def _provider(**kwargs: object) -> MockDnsProvider:
    return MockDnsProvider(now=lambda: FIXED_NOW, **kwargs)  # type: ignore[arg-type]


def test_same_seed_and_clock_give_identical_data() -> None:
    assert _provider(seed=1).list_clients() == _provider(seed=1).list_clients()
    assert _provider(seed=1).get_summary() == _provider(seed=1).get_summary()


def test_different_seeds_give_different_counters() -> None:
    assert _provider(seed=1).get_summary() != _provider(seed=2).get_summary()


def test_sixteen_sample_clients_use_documentation_address_space_only() -> None:
    clients = _provider().list_clients()
    assert len(clients) == len(SAMPLE_DEVICE_NAMES) == 16
    for client in clients:
        assert all(address in DOC_V4 for address in client.ipv4_addresses)
        assert all(address in DOC_V6 for address in client.ipv6_addresses)
        assert client.mac is not None and client.mac.startswith("00:00:5e:00:53:")
        assert client.hostname is not None and client.hostname.endswith(".example")


def test_summary_aggregates_clients() -> None:
    provider = _provider()
    clients = provider.list_clients()
    summary = provider.get_summary()
    assert summary.total_queries == sum(c.total_queries for c in clients)
    assert summary.blocked_queries == sum(c.blocked_queries for c in clients)
    assert summary.unique_clients == 16
    assert summary.collected_at == FIXED_NOW
    assert 0 < summary.block_percentage < 100


def test_health_status_can_be_simulated() -> None:
    assert _provider().health().status is HealthStatus.OK
    assert _provider(health_status=HealthStatus.DOWN).health().status is HealthStatus.DOWN


def test_query_log_for_unknown_client_is_empty() -> None:
    from datetime import timedelta
    from ipaddress import IPv4Address, IPv6Address

    from home_dns.core.models import QueryFilter

    provider = _provider()
    window = {"since": FIXED_NOW - timedelta(minutes=10), "until": FIXED_NOW}
    for address in (IPv4Address("192.0.2.200"), IPv6Address("2001:db8::ffff:ffff")):
        assert provider.query_log(QueryFilter(**window, client_address=address)).entries == ()
