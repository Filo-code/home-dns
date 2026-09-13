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
