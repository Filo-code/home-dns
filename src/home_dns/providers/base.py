"""The DnsProvider interface.

Every implementation (MockDnsProvider now, PiHoleV6Provider in phase C2) must pass the
shared contract tests in tests/contract/. Implementations receive plain values, never
configuration objects, and raise ProviderError subclasses instead of transport errors.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from home_dns.core.blocklists import BlockEntry
from home_dns.core.models import (
    BlocklistDeployment,
    DnsClient,
    DnsSummary,
    DomainLookup,
    ProviderHealth,
    QueryFilter,
    QueryPage,
    SystemMetrics,
)


class ProviderError(Exception):
    """Base class for all provider failures."""


class ProviderUnavailableError(ProviderError):
    """The provider cannot be reached or did not answer."""


class ProviderNotAvailableError(ProviderError):
    """The requested provider implementation does not exist yet."""


class DnsProvider(ABC):
    """Mutating operations take ``dry_run: bool = True`` and change nothing when dry-running."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable identifier, e.g. 'mock' or 'pihole_v6'."""

    @abstractmethod
    def health(self) -> ProviderHealth:
        """Report provider health without raising for an unhealthy provider."""

    @abstractmethod
    def get_summary(self) -> DnsSummary:
        """Aggregate query counters."""

    @abstractmethod
    def list_clients(self) -> list[DnsClient]:
        """Known clients, ordered by client_id."""

    @abstractmethod
    def deploy_blocklist(
        self, source_id: str, entries: frozenset[BlockEntry], *, dry_run: bool = True
    ) -> BlocklistDeployment:
        """Replace all entries of one blocklist source with a validated artifact."""

    @abstractmethod
    def lookup_domain(self, domain: str) -> DomainLookup:
        """Whether a normalized domain is blocked by deployed blocklists, and by which sources."""

    @abstractmethod
    def query_log(
        self, query: QueryFilter, *, limit: int = 100, cursor: str | None = None
    ) -> QueryPage:
        """Queries in ``[query.since, query.until)``, newest first, at most ``limit`` per page.

        ``cursor`` is opaque: only a ``next_cursor`` from a previous page with the same filter.
        Raises ValueError for an unknown cursor or a limit outside 1..1000.
        """

    @abstractmethod
    def system_metrics(self) -> SystemMetrics:
        """Host metrics of the machine running the DNS server."""
