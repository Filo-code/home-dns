"""Dashboard read views and device updates. Roles and data exposure: a7-backend.md §7-§8."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import datetime, timedelta
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import AwareDatetime, BaseModel, Field

from home_dns.api.auth import AdminSession, Context, Session
from home_dns.config.settings import AppSettings
from home_dns.core.filtering import FilteringConfig
from home_dns.core.metrics import Resolution, Rollup, bucket_end, bucket_start
from home_dns.core.models import (
    HealthStatus,
    QueryFilter,
    QueryLogEntry,
    QueryOutcome,
    QueryPage,
    SystemMetrics,
)
from home_dns.core.monitoring import IncidentState, Severity
from home_dns.core.storage import DiskUsage, RetentionPolicy, StorageThresholds
from home_dns.providers.base import DnsProvider, ProviderError
from home_dns.storage.dashboard import DeviceRecord

router = APIRouter(prefix="/api/v1", tags=["dashboard"])

_DAY = timedelta(hours=24)
_QPS_WINDOW = timedelta(minutes=5)
_DEFAULT_SPAN = {
    Resolution.MINUTE: timedelta(hours=1),
    Resolution.HOUR: timedelta(hours=24),
    Resolution.DAY: timedelta(days=30),
}
_MAX_SPAN = {
    Resolution.MINUTE: timedelta(hours=48),
    Resolution.HOUR: timedelta(days=31),
    Resolution.DAY: timedelta(days=400),
}
_ACTIVITY_MAX_ENTRIES = 2000
_TOP = 10
_RECENT = 50


def get_provider(request: Request) -> DnsProvider:
    provider: DnsProvider = request.app.state.provider
    return provider


Provider = Annotated[DnsProvider, Depends(get_provider)]


# ------------------------------------------------------------------------------ schemas


class Counters(BaseModel):
    total: int
    blocked: int
    allowed: int
    cached: int
    forwarded: int
    block_percentage: float
    cache_hit_ratio: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    blocked_by_source: dict[str, int]


def _counters(rollup: Rollup) -> Counters:
    return Counters(
        total=rollup.total,
        blocked=rollup.blocked,
        allowed=rollup.total - rollup.blocked,
        cached=rollup.cached,
        forwarded=rollup.forwarded,
        block_percentage=rollup.block_percentage,
        cache_hit_ratio=rollup.cache_hit_ratio,
        latency_p50_ms=rollup.latency_percentile(50),
        latency_p95_ms=rollup.latency_percentile(95),
        blocked_by_source=dict(sorted(rollup.blocked_by_source.items())),
    )


def _merged(rollups: Iterable[Rollup]) -> Rollup:
    total = Rollup()
    for rollup in rollups:
        total.merge(rollup)
    return total


class ProviderStatus(BaseModel):
    name: str
    status: HealthStatus


class OverviewResponse(BaseModel):
    provider: ProviderStatus
    metrics_as_of: datetime | None = Field(
        description="Collector watermark of the last flush; newer queries are not counted yet"
    )
    window_start: datetime
    last_24h: Counters
    queries_per_second: float = Field(description="Average over the last 5 flushed minutes")
    system: SystemMetrics | None
    open_incidents: int
    last_backup_at: datetime | None
    last_blocklist_update_at: datetime | None
    storage: DiskUsage


class DeviceView(BaseModel):
    device_id: int
    name: str
    custom_name: str | None
    hostname: str | None
    mac: str | None
    addresses: list[str]
    group_id: str
    first_seen: datetime
    last_seen: datetime
    last_24h: Counters


class DeviceUpdate(BaseModel):
    custom_name: str | None = Field(default=None, max_length=64)
    group_id: str | None = None


class DomainCount(BaseModel):
    domain: str
    count: int


class DeviceActivity(BaseModel):
    device_id: int
    since: datetime
    truncated: bool = Field(description="More entries existed than were scanned")
    top_domains: list[DomainCount]
    top_blocked: list[DomainCount]
    recent: list[QueryLogEntry]


class HistoryPoint(BaseModel):
    bucket_start: datetime
    bucket_end: datetime
    queries_per_second: float
    counters: Counters


class HistoryResponse(BaseModel):
    resolution: Resolution
    since: datetime
    until: datetime
    device_id: int | None
    points: list[HistoryPoint] = Field(description="Buckets without queries are omitted")


class IncidentView(BaseModel):
    check_name: str
    state: IncidentState
    opened_at: datetime | None
    last_change_at: datetime | None


class IncidentEventView(BaseModel):
    """One persisted opened/recovered transition. Deliberately minimal — see
    storage/dashboard.py's ``incident_events`` table doc. No "notified" flag: the CLI monitoring
    command does not itself confirm a Telegram send, so that status is not actually known here and
    is not fabricated."""

    check_name: str
    transition: str
    occurred_at: datetime
    severity: Severity | None


# ------------------------------------------------------------------------------ helpers


def _view(device: DeviceRecord, rollup: Rollup) -> DeviceView:
    return DeviceView(
        device_id=device.device_id,
        name=device.custom_name or device.hostname or (device.addresses or ("?",))[0],
        custom_name=device.custom_name,
        hostname=device.hostname,
        mac=device.mac,
        addresses=list(device.addresses),
        group_id=device.group_id,
        first_seen=device.first_seen,
        last_seen=device.last_seen,
        last_24h=_counters(rollup),
    )


def _day_window(context: Context) -> tuple[datetime, datetime]:
    now = context.now()
    return bucket_start(now - _DAY, Resolution.HOUR, context.tz), now


def _device_or_404(context: Context, device_id: int) -> DeviceRecord:
    device = context.store.get_device(device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")
    return device


def _provider_unavailable() -> HTTPException:
    # Never echo the provider exception: it may contain internal URLs.
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "DNS provider unavailable")


# ------------------------------------------------------------------------------- routes


@router.get("/overview", response_model=OverviewResponse)
def overview(_: Session, context: Context, provider: Provider) -> OverviewResponse:
    try:
        health = provider.health().status
    except ProviderError:
        health = HealthStatus.DOWN
    try:
        system = provider.system_metrics()
    except ProviderError:
        system = None
    since, until = _day_window(context)
    as_of = context.store.load_watermark()
    qps = 0.0
    if as_of is not None:
        recent = context.store.rollups(Resolution.MINUTE, as_of - _QPS_WINDOW, as_of)
        qps = round(sum(r.total for _, _, r in recent) / _QPS_WINDOW.total_seconds(), 3)
    maintenance = context.status()
    return OverviewResponse(
        provider=ProviderStatus(name=provider.name, status=health),
        metrics_as_of=as_of,
        window_start=since,
        last_24h=_counters(
            _merged(r for _, _, r in context.store.rollups(Resolution.HOUR, since, until))
        ),
        queries_per_second=qps,
        system=system,
        open_incidents=sum(1 for i in maintenance.incidents if i.state is not IncidentState.OK),
        last_backup_at=maintenance.last_backup_at,
        last_blocklist_update_at=maintenance.last_blocklist_update_at,
        storage=context.disk_usage(),
    )


@router.get("/devices", response_model=list[DeviceView])
def list_devices(_: Session, context: Context) -> list[DeviceView]:
    per_device: dict[int, Rollup] = {}
    for _start, device_id, rollup in context.store.rollups(Resolution.HOUR, *_day_window(context)):
        per_device.setdefault(device_id, Rollup()).merge(rollup)
    return [_view(d, per_device.get(d.device_id, Rollup())) for d in context.store.list_devices()]


def _device_view(context: Context, device_id: int) -> DeviceView:
    device = _device_or_404(context, device_id)
    since, until = _day_window(context)
    rows = context.store.rollups(Resolution.HOUR, since, until, device_id=device_id)
    return _view(device, _merged(r for _, _, r in rows))


@router.get("/devices/{device_id}", response_model=DeviceView)
def get_device(device_id: int, _: Session, context: Context) -> DeviceView:
    return _device_view(context, device_id)


@router.patch("/devices/{device_id}", response_model=DeviceView)
def update_device(
    device_id: int, body: DeviceUpdate, _: AdminSession, context: Context
) -> DeviceView:
    _device_or_404(context, device_id)
    if "group_id" in body.model_fields_set:
        if body.group_id not in context.filtering.group_ids():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown group_id")
        context.store.assign_group(device_id, body.group_id)
    if "custom_name" in body.model_fields_set:
        context.store.rename_device(device_id, (body.custom_name or "").strip() or None)
    return _device_view(context, device_id)


@router.get("/devices/{device_id}/activity", response_model=DeviceActivity)
def device_activity(
    device_id: int, _: AdminSession, context: Context, provider: Provider
) -> DeviceActivity:
    device = _device_or_404(context, device_id)
    until = context.now()
    since = until - _DAY
    entries: list[QueryLogEntry] = []
    try:
        for address in device.addresses:
            query = QueryFilter(since=since, until=until, client_address=ip_address(address))
            cursor = None
            # Reading one entry past the cap is how truncation is detected.
            while len(entries) <= _ACTIVITY_MAX_ENTRIES:
                page = provider.query_log(query, limit=1000, cursor=cursor)
                entries.extend(page.entries)
                cursor = page.next_cursor
                if cursor is None:
                    break
    except ProviderError as exc:
        raise _provider_unavailable() from exc
    truncated = len(entries) > _ACTIVITY_MAX_ENTRIES
    entries = sorted(entries, key=lambda e: (e.time, e.id), reverse=True)[:_ACTIVITY_MAX_ENTRIES]
    allowed = Counter(e.domain for e in entries if e.outcome is not QueryOutcome.BLOCKED)
    blocked = Counter(e.domain for e in entries if e.outcome is QueryOutcome.BLOCKED)
    return DeviceActivity(
        device_id=device_id,
        since=since,
        truncated=truncated,
        top_domains=[DomainCount(domain=d, count=c) for d, c in allowed.most_common(_TOP)],
        top_blocked=[DomainCount(domain=d, count=c) for d, c in blocked.most_common(_TOP)],
        recent=entries[:_RECENT],
    )


@router.get("/metrics/history", response_model=HistoryResponse)
def metrics_history(
    _: Session,
    context: Context,
    resolution: Resolution = Resolution.HOUR,
    since: AwareDatetime | None = None,
    until: AwareDatetime | None = None,
    device_id: int | None = None,
) -> HistoryResponse:
    until = until or context.now()
    since = since or until - _DEFAULT_SPAN[resolution]
    if since >= until:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "since must be before until")
    if until - since > _MAX_SPAN[resolution]:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"window too large for {resolution.value} resolution",
        )
    buckets: dict[datetime, Rollup] = {}
    for start, _device, rollup in context.store.rollups(
        resolution, since, until, device_id=device_id
    ):
        buckets.setdefault(start, Rollup()).merge(rollup)
    points = []
    for start, rollup in sorted(buckets.items()):
        end = bucket_end(start, resolution, context.tz)
        points.append(
            HistoryPoint(
                bucket_start=start,
                bucket_end=end,
                queries_per_second=round(rollup.total / (end - start).total_seconds(), 4),
                counters=_counters(rollup),
            )
        )
    return HistoryResponse(
        resolution=resolution, since=since, until=until, device_id=device_id, points=points
    )


@router.get("/queries", response_model=QueryPage)
def queries(
    _: AdminSession,
    context: Context,
    provider: Provider,
    since: AwareDatetime | None = None,
    until: AwareDatetime | None = None,
    client: IPv4Address | IPv6Address | None = None,
    domain: Annotated[str | None, Query(max_length=253)] = None,
    outcome: QueryOutcome | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    cursor: Annotated[str | None, Query(max_length=64)] = None,
) -> QueryPage:
    until = until or context.now()
    since = since or until - timedelta(hours=1)
    if since > until:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "since must not be after until")
    query = QueryFilter(
        since=since, until=until, client_address=client, domain=domain, outcome=outcome
    )
    try:
        return provider.query_log(query, limit=limit, cursor=cursor)
    except ProviderError as exc:
        raise _provider_unavailable() from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid cursor") from exc


@router.get("/alerts", response_model=list[IncidentView])
def alerts(_: Session, context: Context) -> list[IncidentView]:
    return [
        IncidentView(
            check_name=i.check_name,
            state=i.state,
            opened_at=i.opened_at,
            last_change_at=i.last_change_at,
        )
        for i in context.status().incidents
        if i.state is not IncidentState.OK
    ]


@router.get("/incidents/history", response_model=list[IncidentEventView])
def incident_history(
    _: Session,
    context: Context,
    limit: Annotated[int, Query(ge=1, le=200)] = 30,
    since: AwareDatetime | None = None,
) -> list[IncidentEventView]:
    return [
        IncidentEventView(
            check_name=e.check_name,
            transition=e.transition,
            occurred_at=e.occurred_at,
            severity=e.severity,
        )
        for e in context.store.list_incident_events(since=since, limit=limit)
    ]


@router.get("/config")
def config(_: Session, context: Context) -> dict[str, Any]:
    """A shallow, per-request enrichment of the cached ``config_view`` with live per-source
    blocklist-freshness timestamps — the base view is built once at startup (see
    ``build_config_view``), so a live timestamp cannot be baked into it without going stale."""
    freshness = context.blocklist_freshness()
    view = dict(context.config_view)
    view["blocklist_sources"] = [
        {**source, "last_activated_at": freshness.get(source["id"])}
        for source in view["blocklist_sources"]
    ]
    return view


def build_config_view(
    settings: AppSettings,
    filtering: FilteringConfig,
    thresholds: StorageThresholds,
    retention: RetentionPolicy,
) -> dict[str, Any]:
    """Read-only, sanitized configuration for the dashboard. Built from an allowlist of fields,
    never by dumping settings, so a future secret field cannot leak by accident."""
    metrics = settings.metrics
    return {
        "dns_provider": settings.dns_provider.kind.value,
        "notifier": settings.notifier.kind.value,
        "groups": [
            {"id": g.id, "description": g.description, "policy": g.policy} for g in filtering.groups
        ],
        "policies": [p.model_dump(mode="json") for p in filtering.policies],
        "blocklist_sources": [
            {
                "id": s.id,
                "name": s.name,
                "categories": [c.value for c in s.categories],
                "update_interval_hours": s.update_interval_hours,
            }
            for s in filtering.sources
        ],
        "storage": {
            "thresholds_percent": thresholds.model_dump(mode="json"),
            "retention": retention.model_dump(mode="json"),
        },
        "metrics": {
            "poll_interval_seconds": metrics.poll_interval_seconds,
            "flush_interval_seconds": metrics.flush_interval_seconds,
            "timezone": metrics.timezone,
            "minute_retention_hours": metrics.minute_retention_hours,
            "hour_retention_days": retention.query_history_days,
            "day_retention_days": metrics.day_retention_days,
        },
    }
