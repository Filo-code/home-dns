from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from home_dns.core.models import DnsClient, DnsSummary

NOW = datetime(2026, 9, 13, tzinfo=UTC)


def _client(**overrides: object) -> DnsClient:
    values: dict[str, object] = {
        "client_id": "pc-01",
        "first_seen": NOW - timedelta(days=1),
        "last_seen": NOW,
        "total_queries": 10,
        "blocked_queries": 1,
    }
    values.update(overrides)
    return DnsClient(**values)  # type: ignore[arg-type]


def test_mac_is_normalised() -> None:
    assert _client(mac="00-00-5E-00-53-0A").mac == "00:00:5e:00:53:0a"


@pytest.mark.parametrize(
    "overrides",
    [
        {"mac": "not-a-mac"},
        {"last_seen": NOW - timedelta(days=2)},
        {"blocked_queries": 11},
        {"first_seen": datetime(2026, 9, 12)},  # naive
        {"client_id": ""},
    ],
)
def test_invalid_clients_are_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _client(**overrides)


@pytest.mark.parametrize(("total", "blocked", "cached"), [(10, 11, 0), (10, 0, 11), (-1, 0, 0)])
def test_invalid_summaries_are_rejected(total: int, blocked: int, cached: int) -> None:
    with pytest.raises(ValidationError):
        DnsSummary(
            total_queries=total,
            blocked_queries=blocked,
            cached_queries=cached,
            unique_clients=1,
            collected_at=NOW,
        )


def test_block_percentage() -> None:
    summary = DnsSummary(
        total_queries=0, blocked_queries=0, cached_queries=0, unique_clients=0, collected_at=NOW
    )
    assert summary.block_percentage == 0.0
    assert (
        summary.model_copy(update={"total_queries": 3, "blocked_queries": 1}).block_percentage
        == 33.33
    )
