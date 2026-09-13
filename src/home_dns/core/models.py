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
