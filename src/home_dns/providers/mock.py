"""Deterministic in-memory DNS provider for development and tests.

Uses only documentation address space so no real network data can leak into fixtures:
IPv4 192.0.2.0/24 (RFC 5737), IPv6 2001:db8::/32 (RFC 3849), MAC 00:00:5e:00:53:xx
(RFC 7042) and hostnames under .example (RFC 2606).
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Iterable
from dataclasses import dataclass
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
    QueryFilter,
    QueryLogEntry,
    QueryOutcome,
    QueryPage,
    SystemMetrics,
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

# Source ids match config/blocklists/sources.yaml so source lookups work end to end.
MOCK_BLOCK_SOURCES: tuple[str, ...] = ("hagezi-multi-pro", "hagezi-tif-mini")
_ALLOWED_DOMAINS: tuple[str, ...] = (
    "www.search.example", "video.cdn.example", "api.social.example", "mail.example",
    "store.console.example", "updates.os.example", "chat.messaging.example", "news.example",
)  # fmt: skip
_BLOCKED_DOMAINS: tuple[str, ...] = (
    "ads.adnetwork.example", "pixel.tracker.example", "telemetry.vendor.example",
    "login.phish.example",
)  # fmt: skip
_QUERY_TYPES: tuple[str, ...] = ("A", "AAAA", "HTTPS")
_MAX_QUERIES_PER_DEVICE_MINUTE = 19  # keeps ids unique: see _query_id
_MAX_PAGE = 1000


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _ipv6_for_day(index: int, day: int) -> IPv6Address:
    """A temporary IPv6 address that rotates daily, still inside 2001:db8::/32."""
    return IPv6Address(_IPV6_BASE + (day << 16) + index)


def _query_id(second: int, device_index: int, seq: int) -> int:
    # Ordering by id equals ordering by time, like Pi-hole's database ids.
    return second * 1000 + device_index * 20 + seq


@dataclass(frozen=True)
class _RawQuery:
    id: int
    second: int
    device_index: int
    use_ipv6: bool
    domain: str
    query_type: str
    outcome: QueryOutcome
    blocked_by: str | None
    latency_ms: float


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
        today = int(now.timestamp()) // 86400
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
                    # today's and yesterday's temporary address, like a network table would hold
                    ipv6_addresses=(
                        _ipv6_for_day(index, today),
                        _ipv6_for_day(index, today - 1),
                    ),
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

    # ------------------------------------------------------------------ A7: query log, system

    def _minute_queries(self, minute: int, devices: Iterable[int]) -> list[_RawQuery]:
        """Every query of one epoch minute, regenerated identically on every call."""
        raws = []
        for index in devices:
            rng = random.Random(f"{self._seed}:{index}:{minute}")  # noqa: S311 - fixtures
            count = rng.choices(range(6), weights=(30, 25, 20, 12, 8, 5))[0]
            for seq in range(min(count, _MAX_QUERIES_PER_DEVICE_MINUTE)):
                second = minute * 60 + rng.randrange(60)
                roll = rng.random()
                if roll < 0.15:
                    outcome, domain = QueryOutcome.BLOCKED, rng.choice(_BLOCKED_DOMAINS)
                    blocked_by: str | None = rng.choices(MOCK_BLOCK_SOURCES, weights=(85, 15))[0]
                    latency = rng.uniform(0.05, 0.5)
                elif roll < 0.60:
                    outcome, domain, blocked_by = QueryOutcome.CACHED, "", None
                    latency = rng.uniform(0.05, 1.5)
                else:
                    outcome, domain, blocked_by = QueryOutcome.FORWARDED, "", None
                    latency = min(rng.lognormvariate(3.0, 0.8), 2000.0)
                raws.append(
                    _RawQuery(
                        id=_query_id(second, index, seq),
                        second=second,
                        device_index=index,
                        use_ipv6=rng.random() < 0.3,
                        domain=domain or rng.choice(_ALLOWED_DOMAINS),
                        query_type=rng.choice(_QUERY_TYPES),
                        outcome=outcome,
                        blocked_by=blocked_by,
                        latency_ms=round(latency, 3),
                    )
                )
        return raws

    @staticmethod
    def _address(raw: _RawQuery) -> IPv4Address | IPv6Address:
        if raw.use_ipv6:
            return _ipv6_for_day(raw.device_index, raw.second // 86400)
        return IPv4Address(_IPV4_BASE + raw.device_index)

    @staticmethod
    def _devices_for(address: IPv4Address | IPv6Address | None) -> Iterable[int]:
        """Only generate the device an address can belong to; the address filter stays exact."""
        count = len(SAMPLE_DEVICE_NAMES)
        if address is None:
            return range(count)
        if address.version == 4:
            index = int(address) - _IPV4_BASE
        else:
            index = (int(address) - _IPV6_BASE) & 0xFFFF
        return (index,) if 0 <= index < count else ()

    def _to_entry(self, raw: _RawQuery) -> QueryLogEntry:
        return QueryLogEntry(
            id=raw.id,
            time=datetime.fromtimestamp(raw.second, UTC),
            client_address=self._address(raw),
            domain=raw.domain,
            query_type=raw.query_type,
            outcome=raw.outcome,
            blocked_by=raw.blocked_by,
            latency_ms=raw.latency_ms,
        )

    def query_log(
        self, query: QueryFilter, *, limit: int = 100, cursor: str | None = None
    ) -> QueryPage:
        if not 1 <= limit <= _MAX_PAGE:
            raise ValueError(f"limit must be 1..{_MAX_PAGE}")
        if cursor is not None and not cursor.isdecimal():
            raise ValueError(f"invalid cursor {cursor!r}")
        since = math.ceil(query.since.timestamp())
        until = math.ceil(query.until.timestamp())  # whole seconds: second < until is exclusive
        below_id = int(cursor) if cursor is not None else None
        top_second = until - 1 if below_id is None else min(until - 1, below_id // 1000)

        devices = self._devices_for(query.client_address)
        found: list[QueryLogEntry] = []
        minute = top_second // 60
        while minute * 60 + 59 >= since and top_second >= since and len(found) <= limit:
            raws = sorted(self._minute_queries(minute, devices), key=lambda r: r.id, reverse=True)
            for raw in raws:
                if (
                    since <= raw.second < until
                    and (below_id is None or raw.id < below_id)
                    and (query.client_address is None or self._address(raw) == query.client_address)
                    and (query.domain is None or raw.domain == query.domain)
                    and (query.outcome is None or raw.outcome is query.outcome)
                ):
                    found.append(self._to_entry(raw))
            minute -= 1

        page = tuple(found[:limit])
        next_cursor = str(page[-1].id) if len(found) > limit else None
        return QueryPage(entries=page, next_cursor=next_cursor)

    def system_metrics(self) -> SystemMetrics:
        now = self._now()
        rng = random.Random(f"{self._seed}:system:{int(now.timestamp()) // 60}")  # noqa: S311
        total = 4 * 1024**3
        return SystemMetrics(
            uptime_seconds=3 * 86400 + int(now.timestamp()) % 86400,
            cpu_percent=round(rng.uniform(2, 15), 1),
            load_1m=round(rng.uniform(0.05, 0.6), 2),
            memory_total_bytes=total,
            memory_used_bytes=int(rng.uniform(0.15, 0.25) * total),
            temperature_celsius=round(rng.uniform(44, 58), 1),
            collected_at=now,
        )
