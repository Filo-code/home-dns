"""Metrics collector: poll the provider, aggregate in RAM, flush in batches.

See docs/specs/a7-backend.md §4 (device identity) and §6 (collector and disk writes). The
watermark is persisted in the same transaction as the rollups, so a crash loses nothing: the
next start re-reads the provider's own log from the last stored watermark.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from home_dns.core.metrics import Resolution, Rollup, bucket_start
from home_dns.core.models import DnsClient, QueryFilter, QueryLogEntry
from home_dns.providers.base import DnsProvider, ProviderError
from home_dns.storage.dashboard import DashboardStore, DeviceUpsert, FlushBatch

logger = logging.getLogger(__name__)

_PAGE_SIZE = 1000


@dataclass(frozen=True)
class RetentionWindows:
    minute: timedelta = timedelta(hours=48)
    hour: timedelta = timedelta(days=30)
    day: timedelta = timedelta(days=365)


@dataclass
class _Device:
    mac: str | None
    hostname: str | None
    first_seen: datetime
    last_seen: datetime


class DeviceRegistry:
    """In-memory identity map, loaded from the store; the collector is its only writer."""

    def __init__(self, store: DashboardStore) -> None:
        self._devices: dict[int, _Device] = {}
        self._by_mac: dict[str, int] = {}
        for record in store.list_devices():
            self._devices[record.device_id] = _Device(
                record.mac, record.hostname, record.first_seen, record.last_seen
            )
            if record.mac:
                self._by_mac[record.mac] = record.device_id
        self._by_address = store.address_bindings()
        self._dirty_devices: set[int] = set()
        self._dirty_addresses: dict[str, datetime] = {}

    def _new(self, mac: str | None, hostname: str | None, first: datetime, last: datetime) -> int:
        device_id = max(self._devices, default=0) + 1
        self._devices[device_id] = _Device(mac, hostname, first, last)
        if mac:
            self._by_mac[mac] = device_id
        self._dirty_devices.add(device_id)
        return device_id

    def _bind(self, address: str, device_id: int, seen: datetime) -> None:
        self._by_address[address] = device_id
        previous = self._dirty_addresses.get(address)
        self._dirty_addresses[address] = max(previous, seen) if previous else seen

    def observe_client(self, client: DnsClient) -> int:
        """MAC first, then an address held by a device without a different MAC, else new."""
        addresses = [str(a) for a in (*client.ipv4_addresses, *client.ipv6_addresses)]
        device_id = self._by_mac.get(client.mac) if client.mac else None
        if device_id is None:
            for address in addresses:
                candidate = self._by_address.get(address)
                if candidate is not None and self._devices[candidate].mac in (None, client.mac):
                    device_id = candidate
                    break
        if device_id is None:
            device_id = self._new(client.mac, client.hostname, client.first_seen, client.last_seen)
        device = self._devices[device_id]
        if client.mac and device.mac is None:
            device.mac = client.mac
            self._by_mac[client.mac] = device_id
            self._dirty_devices.add(device_id)
        if client.hostname and client.hostname != device.hostname:
            device.hostname = client.hostname
            self._dirty_devices.add(device_id)
        for address in addresses:
            self._bind(address, device_id, client.last_seen)
        return device_id

    def resolve_address(self, address: str, seen: datetime) -> int:
        device_id = self._by_address.get(address)
        if device_id is None:
            device_id = self._new(None, None, seen, seen)
        device = self._devices[device_id]
        if seen > device.last_seen:
            device.last_seen = seen
            self._dirty_devices.add(device_id)
        self._bind(address, device_id, seen)
        return device_id

    def pending(self) -> tuple[tuple[DeviceUpsert, ...], tuple[tuple[str, int, datetime], ...]]:
        devices = tuple(
            DeviceUpsert(i, d.mac, d.hostname, d.first_seen, d.last_seen)
            for i in sorted(self._dirty_devices)
            for d in (self._devices[i],)
        )
        addresses = tuple(
            (address, self._by_address[address], seen)
            for address, seen in sorted(self._dirty_addresses.items())
        )
        return devices, addresses

    def mark_flushed(self) -> None:
        """Only after the store committed; a failed flush keeps everything for the retry."""
        self._dirty_devices.clear()
        self._dirty_addresses.clear()


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Collector:
    def __init__(
        self,
        provider: DnsProvider,
        store: DashboardStore,
        *,
        tz: ZoneInfo,
        retention: RetentionWindows | None = None,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._provider = provider
        self._store = store
        self._tz = tz
        self._retention = retention or RetentionWindows()
        self._now = now
        self._registry = DeviceRegistry(store)
        self._watermark = store.load_watermark()
        self._pending: dict[tuple[datetime, int], Rollup] = {}

    def poll(self) -> int:
        """Aggregate queries since the watermark. Returns how many were read.

        On a provider error nothing is aggregated and the watermark stays put, so the same
        window is retried on the next poll without double counting.
        """
        until = self._now().replace(microsecond=0)
        if self._watermark is None:  # first start ever: no backfill
            self._watermark = until
            return 0
        if until <= self._watermark:
            return 0
        try:
            clients = self._provider.list_clients()
            entries = self._read_window(QueryFilter(since=self._watermark, until=until))
        except ProviderError as exc:
            logger.warning("collector poll failed, will retry the same window: %s", exc)
            return 0
        for client in clients:
            self._registry.observe_client(client)
        for entry in entries:
            device_id = self._registry.resolve_address(str(entry.client_address), entry.time)
            key = (bucket_start(entry.time, Resolution.MINUTE, self._tz), device_id)
            self._pending.setdefault(key, Rollup()).add(entry)
        self._watermark = until
        return len(entries)

    def _read_window(self, query: QueryFilter) -> list[QueryLogEntry]:
        entries: list[QueryLogEntry] = []
        cursor = None
        while True:
            page = self._provider.query_log(query, limit=_PAGE_SIZE, cursor=cursor)
            entries.extend(page.entries)
            if page.next_cursor is None:
                return entries
            cursor = page.next_cursor

    def flush(self) -> None:
        if self._watermark is None:
            return
        now = self._now()
        rollups = tuple(
            (resolution, bucket_start(minute, resolution, self._tz), device_id, rollup)
            for (minute, device_id), rollup in sorted(self._pending.items())
            for resolution in Resolution
        )
        devices, addresses = self._registry.pending()
        self._store.flush(
            FlushBatch(
                watermark=self._watermark,
                devices=devices,
                addresses=addresses,
                rollups=rollups,
                retention_cutoffs={
                    Resolution.MINUTE: now - self._retention.minute,
                    Resolution.HOUR: now - self._retention.hour,
                    Resolution.DAY: now - self._retention.day,
                },
            )
        )
        self._registry.mark_flushed()
        self._pending.clear()

    def run(self, stop: threading.Event, *, poll_interval: float, flush_interval: float) -> None:
        """Loop until ``stop`` is set, then poll and flush once more."""
        last_flush = self._now()
        while not stop.wait(poll_interval):
            try:
                self.poll()
                if (self._now() - last_flush).total_seconds() >= flush_interval:
                    self.flush()
                    last_flush = self._now()
            except Exception:  # a metrics failure must never take the API down
                logger.exception("collector cycle failed")
        try:
            self.poll()
            self.flush()
        except Exception:
            logger.exception("final collector flush failed")
