"""Behaviour every DnsProvider implementation must satisfy."""

from home_dns.core.models import DnsClient, DnsSummary, HealthStatus, ProviderHealth
from home_dns.providers.base import DnsProvider


def test_name_is_a_stable_identifier(provider: DnsProvider) -> None:
    assert provider.name
    assert provider.name == provider.name.strip().lower()


def test_health_returns_a_status(provider: DnsProvider) -> None:
    health = provider.health()
    assert isinstance(health, ProviderHealth)
    assert health.status in set(HealthStatus)


def test_summary_is_consistent(provider: DnsProvider) -> None:
    summary = provider.get_summary()
    assert isinstance(summary, DnsSummary)
    assert summary.blocked_queries <= summary.total_queries
    assert summary.collected_at.tzinfo is not None


def test_clients_are_valid_unique_and_ordered(provider: DnsProvider) -> None:
    clients = provider.list_clients()
    assert all(isinstance(c, DnsClient) for c in clients)
    ids = [c.client_id for c in clients]
    assert len(ids) == len(set(ids))
    assert ids == sorted(ids)
    for client in clients:
        assert client.ipv4_addresses or client.ipv6_addresses
        assert client.first_seen <= client.last_seen


def test_summary_client_count_matches_clients(provider: DnsProvider) -> None:
    assert provider.get_summary().unique_clients == len(provider.list_clients())


# ----------------------------------------------------------------- A2: blocklist deployment

from home_dns.core.blocklists import BlockEntry  # noqa: E402

ENTRIES = frozenset(
    {BlockEntry("ads.contract.example", True), BlockEntry("track.contract.example", False)}
)


def test_dry_run_deployment_changes_nothing(provider: DnsProvider) -> None:
    result = provider.deploy_blocklist("contract-list", ENTRIES)
    assert result.dry_run is True and result.applied is False
    assert result.entries == 2
    assert provider.lookup_domain("ads.contract.example").blocked is False


def test_deployment_blocks_with_subdomain_semantics(provider: DnsProvider) -> None:
    result = provider.deploy_blocklist("contract-list", ENTRIES, dry_run=False)
    assert result.applied is True
    assert provider.lookup_domain("ads.contract.example").matched_sources == ("contract-list",)
    assert provider.lookup_domain("x.ads.contract.example").blocked is True
    assert provider.lookup_domain("track.contract.example").blocked is True
    assert provider.lookup_domain("x.track.contract.example").blocked is False
    assert provider.lookup_domain("contract.example").blocked is False


def test_redeployment_replaces_previous_entries(provider: DnsProvider) -> None:
    provider.deploy_blocklist("contract-list", ENTRIES, dry_run=False)
    provider.deploy_blocklist(
        "contract-list", frozenset({BlockEntry("new.contract.example", True)}), dry_run=False
    )
    assert provider.lookup_domain("ads.contract.example").blocked is False
    assert provider.lookup_domain("new.contract.example").blocked is True


def test_sources_are_independent(provider: DnsProvider) -> None:
    provider.deploy_blocklist("list-one", ENTRIES, dry_run=False)
    provider.deploy_blocklist(
        "list-two", frozenset({BlockEntry("ads.contract.example", True)}), dry_run=False
    )
    assert provider.lookup_domain("ads.contract.example").matched_sources == (
        "list-one",
        "list-two",
    )


# ----------------------------------------------------------------- A7: query log and system

from datetime import UTC, datetime, timedelta  # noqa: E402

import pytest  # noqa: E402

from home_dns.core.models import QueryFilter, QueryOutcome, SystemMetrics  # noqa: E402

# The contract fixtures pin the clock to 2026-09-13T00:00Z; query the 30 minutes before it.
WINDOW_END = datetime(2026, 9, 13, tzinfo=UTC)
WINDOW = QueryFilter(since=WINDOW_END - timedelta(minutes=30), until=WINDOW_END)


def _all_entries(provider: DnsProvider, query: QueryFilter, limit: int) -> list:  # type: ignore[type-arg]
    entries, cursor = [], None
    while True:
        page = provider.query_log(query, limit=limit, cursor=cursor)
        entries.extend(page.entries)
        if page.next_cursor is None:
            return entries
        cursor = page.next_cursor


def test_query_log_respects_half_open_window_and_order(provider: DnsProvider) -> None:
    entries = _all_entries(provider, WINDOW, limit=1000)
    assert entries, "a 30-minute window of 16 active devices cannot be empty"
    assert all(WINDOW.since <= e.time < WINDOW.until for e in entries)
    keys = [(e.time, e.id) for e in entries]
    assert keys == sorted(keys, reverse=True)
    assert len({e.id for e in entries}) == len(entries)


def test_query_log_pagination_is_complete_and_stable(provider: DnsProvider) -> None:
    whole = _all_entries(provider, WINDOW, limit=1000)
    paged = _all_entries(provider, WINDOW, limit=7)
    assert paged == whole


def test_query_log_last_page_has_no_cursor(provider: DnsProvider) -> None:
    empty = QueryFilter(since=WINDOW_END, until=WINDOW_END)
    assert provider.query_log(empty).entries == ()
    assert provider.query_log(empty).next_cursor is None


def test_query_log_filters_narrow_results(provider: DnsProvider) -> None:
    sample = _all_entries(provider, WINDOW, limit=1000)[0]
    by_client = _all_entries(
        provider, WINDOW.model_copy(update={"client_address": sample.client_address}), 1000
    )
    assert by_client and all(e.client_address == sample.client_address for e in by_client)
    blocked = _all_entries(
        provider, WINDOW.model_copy(update={"outcome": QueryOutcome.BLOCKED}), 1000
    )
    assert all(e.outcome is QueryOutcome.BLOCKED for e in blocked)
    by_domain = _all_entries(provider, WINDOW.model_copy(update={"domain": sample.domain}), 1000)
    assert by_domain and all(e.domain == sample.domain for e in by_domain)


def test_query_log_blocked_entries_are_attributed(provider: DnsProvider) -> None:
    for entry in _all_entries(provider, WINDOW, limit=1000):
        if entry.outcome is not QueryOutcome.BLOCKED:
            assert entry.blocked_by is None


@pytest.mark.parametrize("limit", [0, 1001])
def test_query_log_rejects_bad_limit(provider: DnsProvider, limit: int) -> None:
    with pytest.raises(ValueError, match="limit"):
        provider.query_log(WINDOW, limit=limit)


def test_query_log_rejects_malformed_cursor(provider: DnsProvider) -> None:
    with pytest.raises(ValueError, match="cursor"):
        provider.query_log(WINDOW, cursor="not-a-cursor")


def test_client_addresses_seen_in_log_are_known_clients(provider: DnsProvider) -> None:
    known = {
        address
        for client in provider.list_clients()
        for address in (*client.ipv4_addresses, *client.ipv6_addresses)
    }
    assert {e.client_address for e in _all_entries(provider, WINDOW, 1000)} <= known


def test_system_metrics_are_plausible(provider: DnsProvider) -> None:
    metrics = provider.system_metrics()
    assert isinstance(metrics, SystemMetrics)
    assert metrics.memory_total_bytes > 0
    assert metrics.collected_at.tzinfo is not None
