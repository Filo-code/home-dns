"""Everything the dashboard routes need, built once by the composition root (cli ``serve``)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from home_dns.collector import Collector
from home_dns.core.auth import MIN_PASSWORD_LENGTH, LoginRateLimiter, ScryptParams, hash_password
from home_dns.core.filtering import FilteringConfig
from home_dns.core.monitoring import Incident
from home_dns.core.storage import DiskUsage
from home_dns.storage.dashboard import DashboardStore

_EMPTY_DISK_USAGE = DiskUsage(total_bytes=0, used_bytes=0, free_bytes=0)


@dataclass(frozen=True)
class MaintenanceStatus:
    last_backup_at: datetime | None = None
    last_blocklist_update_at: datetime | None = None
    incidents: tuple[Incident, ...] = ()


@dataclass(frozen=True)
class CollectorRunner:
    collector: Collector
    poll_interval_seconds: float
    flush_interval_seconds: float


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class DashboardContext:
    store: DashboardStore
    filtering: FilteringConfig
    config_view: dict[str, Any]
    status: Callable[[], MaintenanceStatus]
    disk_usage: Callable[[], DiskUsage] = lambda: _EMPTY_DISK_USAGE
    blocklist_freshness: Callable[[], dict[str, datetime | None]] = dict
    tz: ZoneInfo = field(default_factory=lambda: ZoneInfo("Europe/Rome"))
    cookie_secure: bool = True
    session_idle: timedelta = timedelta(hours=12)
    session_absolute: timedelta = timedelta(days=7)
    now: Callable[[], datetime] = _utc_now
    password_params: ScryptParams = field(default_factory=ScryptParams)
    collector: CollectorRunner | None = None
    limiter: LoginRateLimiter = field(default_factory=LoginRateLimiter)
    dummy_hash: str = field(init=False)

    def __post_init__(self) -> None:
        # Verified against when the username is unknown, so both cases cost the same time.
        self.dummy_hash = hash_password("x" * MIN_PASSWORD_LENGTH, params=self.password_params)
