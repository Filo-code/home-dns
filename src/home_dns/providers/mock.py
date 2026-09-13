"""Deterministic in-memory DNS provider for development and tests.

Uses only documentation address space so no real network data can leak into fixtures:
IPv4 192.0.2.0/24 (RFC 5737), IPv6 2001:db8::/32 (RFC 3849), MAC 00:00:5e:00:53:xx
(RFC 7042) and hostnames under .example (RFC 2606).
"""

from __future__ import annotations

import random
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address, IPv6Address

from home_dns.core.blocklists import BlockEntry
from home_dns.core.models import (
    BlocklistDeployment,
    DnsClient,
    DnsSummary,
    DomainLookup,
    HealthStatus,
    ProviderHealth,
)
from home_dns.providers.base import DnsProvider

SAMPLE_DEVICE_NAMES: tuple[str, ...] = (
    "pc-01", "pc-02", "pc-03",
    "tv-01", "tv-02", "tv-03",
    "phone-01", "phone-02", "phone-03", "phone-04", "phone-05", "phone-06",
    "tablet-01", "tablet-02", "tablet-03",
    "console-01",
)  # fmt: skip

_IPV4_BASE = int(IPv4Address("192.0.2.10"))
_IPV6_BASE = int(IPv6Address("2001:db8::10"))


def _utc_now() -> datetime:
    return datetime.now(UTC)


class MockDnsProvider(DnsProvider):
    def __init__(
        self,
        *,
        seed: int = 42,
        now: Callable[[], datetime] = _utc_now,
        health_status: HealthStatus = HealthStatus.OK,
    ) -> None:
        self._seed = seed
        self._now = now
        self._health_status = health_status
        self._blocklists: dict[str, frozenset[BlockEntry]] = {}

    @property
    def name(self) -> str:
        return "mock"

    def health(self) -> ProviderHealth:
        return ProviderHealth(status=self._health_status, detail="mock provider")

    def list_clients(self) -> list[DnsClient]:
        rng = random.Random(self._seed)  # noqa: S311 - deterministic fixtures, not security
        now = self._now()
        clients = []
        for index, device in enumerate(SAMPLE_DEVICE_NAMES):
            total = rng.randint(100, 5000)
            blocked = int(total * rng.uniform(0.02, 0.35))
            first_seen = now - timedelta(days=rng.randint(1, 30))
            last_seen = now - timedelta(minutes=rng.randint(0, 120))
            clients.append(
                DnsClient(
                    client_id=device,
                    ipv4_addresses=(IPv4Address(_IPV4_BASE + index),),
                    ipv6_addresses=(IPv6Address(_IPV6_BASE + index),),
                    mac=f"00:00:5e:00:53:{0x10 + index:02x}",
                    hostname=f"{device}.example",
                    first_seen=first_seen,
                    last_seen=max(last_seen, first_seen),
                    total_queries=total,
                    blocked_queries=blocked,
                )
            )
        return sorted(clients, key=lambda client: client.client_id)

    def get_summary(self) -> DnsSummary:
        clients = self.list_clients()
        total = sum(c.total_queries for c in clients)
        return DnsSummary(
            total_queries=total,
            blocked_queries=sum(c.blocked_queries for c in clients),
            cached_queries=total * 3 // 5,
            unique_clients=len(clients),
            collected_at=self._now(),
        )

    def deploy_blocklist(
        self, source_id: str, entries: frozenset[BlockEntry], *, dry_run: bool = True
    ) -> BlocklistDeployment:
        if not dry_run:
            self._blocklists[source_id] = entries
        return BlocklistDeployment(
            source_id=source_id, entries=len(entries), dry_run=dry_run, applied=not dry_run
        )

    def lookup_domain(self, domain: str) -> DomainLookup:
        labels = domain.split(".")
        ancestors = {".".join(labels[i:]) for i in range(1, len(labels))}
        matched = tuple(
            sorted(
                source_id
                for source_id, entries in self._blocklists.items()
                if BlockEntry(domain, False) in entries
                or BlockEntry(domain, True) in entries
                or any(BlockEntry(parent, True) in entries for parent in ancestors)
            )
        )
        return DomainLookup(domain=domain, blocked=bool(matched), matched_sources=matched)
