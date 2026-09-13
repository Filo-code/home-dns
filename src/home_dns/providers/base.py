"""The DnsProvider interface.

Every implementation (MockDnsProvider now, PiHoleV6Provider in phase C2) must pass the
shared contract tests in tests/contract/. Implementations receive plain values, never
configuration objects, and raise ProviderError subclasses instead of transport errors.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from home_dns.core.models import DnsClient, DnsSummary, ProviderHealth


class ProviderError(Exception):
    """Base class for all provider failures."""


class ProviderUnavailableError(ProviderError):
    """The provider cannot be reached or did not answer."""


class ProviderNotAvailableError(ProviderError):
    """The requested provider implementation does not exist yet."""


class DnsProvider(ABC):
    """Read-only in A0. Mutating operations arrive with their models and take dry_run=True."""

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
