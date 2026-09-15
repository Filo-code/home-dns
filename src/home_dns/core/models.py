"""Provider-neutral domain models shared by providers, storage and the API."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from ipaddress import IPv4Address, IPv6Address

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

_MAC_RE = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value


class HealthStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ProviderHealth(_Model):
    status: HealthStatus
    detail: str = ""


class DnsSummary(_Model):
    total_queries: int = Field(ge=0)
    blocked_queries: int = Field(ge=0)
    cached_queries: int = Field(ge=0)
    unique_clients: int = Field(ge=0)
    collected_at: datetime

    _aware = field_validator("collected_at")(_require_aware)

    @model_validator(mode="after")
    def _counts_consistent(self) -> DnsSummary:
        if self.blocked_queries > self.total_queries:
            raise ValueError("blocked_queries cannot exceed total_queries")
        if self.cached_queries > self.total_queries:
            raise ValueError("cached_queries cannot exceed total_queries")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def block_percentage(self) -> float:
        if self.total_queries == 0:
            return 0.0
        return round(100 * self.blocked_queries / self.total_queries, 2)


class DnsClient(_Model):
    client_id: str = Field(min_length=1)
    ipv4_addresses: tuple[IPv4Address, ...] = ()
    ipv6_addresses: tuple[IPv6Address, ...] = ()
    mac: str | None = None
    hostname: str | None = None
    first_seen: datetime
    last_seen: datetime
    total_queries: int = Field(ge=0)
    blocked_queries: int = Field(ge=0)

    _aware = field_validator("first_seen", "last_seen")(_require_aware)

    @field_validator("mac")
    @classmethod
    def _normalise_mac(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalised = value.strip().lower().replace("-", ":")
        if not _MAC_RE.fullmatch(normalised):
            raise ValueError("mac must be six hexadecimal octets")
        return normalised

    @model_validator(mode="after")
    def _consistent(self) -> DnsClient:
        if self.last_seen < self.first_seen:
            raise ValueError("last_seen cannot be earlier than first_seen")
        if self.blocked_queries > self.total_queries:
            raise ValueError("blocked_queries cannot exceed total_queries")
        return self


class BlocklistDeployment(_Model):
    source_id: str = Field(min_length=1)
    entries: int = Field(ge=0)
    dry_run: bool
    applied: bool


class DomainLookup(_Model):
    domain: str
    blocked: bool
    matched_sources: tuple[str, ...] = ()


# ----------------------------------------------------------------- A7: query log and system


class QueryOutcome(StrEnum):
    """Pi-hole's 19 query statuses collapsed; mapping in docs/specs/a7-backend.md §3."""

    FORWARDED = "forwarded"
    CACHED = "cached"
    BLOCKED = "blocked"
    OTHER = "other"


class QueryLogEntry(_Model):
    id: int = Field(ge=0)
    time: datetime
    client_address: IPv4Address | IPv6Address
    domain: str = Field(min_length=1)
    query_type: str = Field(min_length=1)
    outcome: QueryOutcome
    blocked_by: str | None = None
    latency_ms: float | None = Field(default=None, ge=0)
    # Provider-reported reply kind (e.g. "NXDOMAIN", "SERVFAIL", "NODATA"), when the provider
    # exposes it — used only by the optional anomaly-detection layer (core/anomaly.py). None
    # when a provider (e.g. MockDnsProvider) doesn't distinguish reply kinds.
    reply_type: str | None = None

    _aware = field_validator("time")(_require_aware)


class QueryFilter(_Model):
    """Half-open window ``[since, until)``; other fields narrow it further."""

    since: datetime
    until: datetime
    client_address: IPv4Address | IPv6Address | None = None
    domain: str | None = None
    outcome: QueryOutcome | None = None

    _aware = field_validator("since", "until")(_require_aware)

    @model_validator(mode="after")
    def _ordered(self) -> QueryFilter:
        if self.until < self.since:
            raise ValueError("until cannot be earlier than since")
        return self


class QueryPage(_Model):
    """Entries newest first. Pass ``next_cursor`` back to continue; None means no more."""

    entries: tuple[QueryLogEntry, ...]
    next_cursor: str | None = None


class SystemMetrics(_Model):
    uptime_seconds: int = Field(ge=0)
    cpu_percent: float = Field(ge=0, le=100)
    load_1m: float = Field(ge=0)
    memory_total_bytes: int = Field(ge=0)
    memory_used_bytes: int = Field(ge=0)
    temperature_celsius: float | None = None
    collected_at: datetime

    _aware = field_validator("collected_at")(_require_aware)

    @model_validator(mode="after")
    def _memory_consistent(self) -> SystemMetrics:
        if self.memory_used_bytes > self.memory_total_bytes:
            raise ValueError("memory_used_bytes cannot exceed memory_total_bytes")
        return self
