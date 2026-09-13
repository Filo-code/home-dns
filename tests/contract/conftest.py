"""Provider registry for the DnsProvider contract suite.

Every provider listed here must pass tests/contract/test_dns_provider_contract.py unchanged.
PiHoleV6Provider joins in phase C2 (against a temporary local container, opt-in only).
"""

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from home_dns.providers.base import DnsProvider
from home_dns.providers.mock import MockDnsProvider

PROVIDER_FACTORIES: dict[str, Callable[[], DnsProvider]] = {
    "mock": lambda: MockDnsProvider(seed=3, now=lambda: datetime(2026, 9, 13, tzinfo=UTC)),
}


@pytest.fixture(params=sorted(PROVIDER_FACTORIES), ids=str)
def provider(request: pytest.FixtureRequest) -> DnsProvider:
    return PROVIDER_FACTORIES[request.param]()
