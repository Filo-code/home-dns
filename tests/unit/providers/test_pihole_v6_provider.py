"""Unit tests for PiholeV6Provider against a mocked Pi-hole v6 HTTP API.

Response shapes here mirror the real, live instance's actual JSON (captured during the Stage C
lab, see docs/audits/2026-09-15-pihole-v6-provider.md) — not invented schemas.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address

import httpx
import pytest

from home_dns.core.blocklists import BlockEntry
from home_dns.core.models import HealthStatus, QueryFilter, QueryOutcome
from home_dns.providers.base import ProviderUnavailableError
from home_dns.providers.pihole_v6 import (
    AuthenticationError,
    MalformedResponseError,
    PiholeV6Provider,
)

FIXED_NOW = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
GOOD_PASSWORD = "correct-horse"


class FakePihole:
    """A tiny stand-in for the real FTL webserver: enough real-shaped behaviour to drive
    PiholeV6Provider's HTTP calls without a network."""

    def __init__(self) -> None:
        self.password = GOOD_PASSWORD
        self.session_validity = 1800
        self.valid_sids: set[str] = set()
        self._sid_counter = 0
        self.auth_calls = 0
        self.queries: list[dict[str, object]] = []
        self.devices: list[dict[str, object]] = []
        self.summary: dict[str, object] = _default_summary()
        self.system: dict[str, object] = _default_system()
        self.sensors: dict[str, object] | None = _default_sensors()
        self.lists: list[dict[str, object]] = []
        self.deny_domains: list[dict[str, object]] = []
        self.force_500_paths: set[str] = set()
        self.force_timeout_paths: set[str] = set()
        self.search_results: dict[str, dict[str, object]] = {}

    def issue_sid(self) -> str:
        self._sid_counter += 1
        sid = f"sid-{self._sid_counter}"
        self.valid_sids.add(sid)
        return sid

    def handler(self) -> Callable[[httpx.Request], httpx.Response]:
        def handle(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path in self.force_timeout_paths:
                raise httpx.TimeoutException("simulated timeout", request=request)
            if path in self.force_500_paths:
                return httpx.Response(500, json={"error": {"key": "internal", "message": "boom"}})

            if path == "/api/auth" and request.method == "POST":
                self.auth_calls += 1
                body = _json(request)
                if body.get("password") != self.password:
                    return httpx.Response(
                        200,
                        json={
                            "session": {
                                "valid": False,
                                "sid": None,
                                "validity": -1,
                                "message": "password incorrect",
                            }
                        },
                    )
                sid = self.issue_sid()
                return httpx.Response(
                    200,
                    json={
                        "session": {
                            "valid": True,
                            "sid": sid,
                            "validity": self.session_validity,
                            "message": "password correct",
                        }
                    },
                )

            sid = request.headers.get("X-FTL-SID")
            if sid not in self.valid_sids:
                return httpx.Response(
                    401, json={"error": {"key": "unauthorized", "message": "Unauthorized"}}
                )

            if path == "/api/info/ftl":
                return httpx.Response(200, json={"took": 0.001})
            if path == "/api/stats/summary":
                return httpx.Response(200, json=self.summary)
            if path == "/api/info/system":
                return httpx.Response(200, json=self.system)
            if path == "/api/info/sensors":
                if self.sensors is None:
                    return httpx.Response(404, json={"error": {"key": "not_found"}})
                return httpx.Response(200, json=self.sensors)
            if path == "/api/network/devices":
                return httpx.Response(200, json={"devices": self.devices})
            if path == "/api/lists":
                return httpx.Response(200, json={"lists": self.lists})
            if path == "/api/domains/deny":
                return httpx.Response(200, json={"domains": self.deny_domains})
            if path == "/api/domains:batchDelete":
                to_delete = _json_array(request)
                keep = []
                for d in self.deny_domains:
                    if not any(
                        d["domain"] == item["item"] and d["kind"] == item["kind"]
                        for item in to_delete
                    ):
                        keep.append(d)
                self.deny_domains = keep
                return httpx.Response(204)
            if path in ("/api/domains/deny/exact", "/api/domains/deny/regex"):
                kind = "exact" if path.endswith("exact") else "regex"
                body = _json(request)
                added = body["domain"] if isinstance(body["domain"], list) else [body["domain"]]
                for d in added:
                    self.deny_domains.append(
                        {"domain": d, "kind": kind, "comment": body.get("comment")}
                    )
                return httpx.Response(201, json={"domains": [], "took": 0.01})
            if path == "/api/queries":
                return self._handle_queries(request)
            if path.startswith("/api/search/"):
                domain = path.removeprefix("/api/search/")
                result = self.search_results.get(domain, {"search": {"domains": [], "gravity": []}})
                return httpx.Response(200, json=result)
            return httpx.Response(404, json={"error": {"key": "not_found"}})

        return handle

    def _handle_queries(self, request: httpx.Request) -> httpx.Response:
        params = request.url.params
        start = int(params.get("start", "0"))
        length = int(params.get("length", "100"))
        client_ip = params.get("client_ip")
        status_filter = params.get("status")
        domain_filter = params.get("domain")

        matching = self.queries
        if client_ip is not None:
            matching = [q for q in matching if q["client"]["ip"] == client_ip]  # type: ignore[index]
        if status_filter is not None:
            matching = [q for q in matching if q["status"] == status_filter]
        if domain_filter is not None:
            matching = [q for q in matching if q["domain"] == domain_filter]

        page = matching[start : start + length]
        return httpx.Response(
            200,
            json={
                "queries": page,
                "cursor": matching[-1]["id"] if matching else 0,
                "recordsTotal": len(self.queries),
                "recordsFiltered": len(matching),
                "draw": 0,
                "earliest_timestamp": 0,
                "earliest_timestamp_disk": 0,
                "took": 0.001,
            },
        )


def _json(request: httpx.Request) -> dict[str, object]:
    import json as _json_module

    data = _json_module.loads(request.content)
    if not isinstance(data, dict):
        raise TypeError(f"expected a JSON object body, got {type(data).__name__}")
    return data


def _json_array(request: httpx.Request) -> list[dict[str, object]]:
    import json as _json_module

    data = _json_module.loads(request.content)
    if not isinstance(data, list):
        raise TypeError(f"expected a JSON array body, got {type(data).__name__}")
    return data


def _default_summary() -> dict[str, object]:
    return {
        "queries": {
            "total": 100,
            "blocked": 10,
            "status": {"GRAVITY": 10, "FORWARDED": 40, "CACHE": 45, "CACHE_STALE": 5},
        },
        "clients": {"active": 2, "total": 2},
        "gravity": {"domains_being_blocked": 355727, "last_update": 1789450668},
    }


def _default_system() -> dict[str, object]:
    return {
        "system": {
            "uptime": 34002,
            "memory": {"ram": {"total": 3886900, "used": 151344}},
            "cpu": {"nprocs": 4, "%cpu": 3.15, "load": {"raw": [0.1, 0.05, 0.02]}},
        }
    }


def _default_sensors() -> dict[str, object]:
    return {"sensors": {"cpu_temp": 41.4}}


def _query(
    id_: int, *, client_ip: str, domain: str, status: str, time_: float, latency: float = 0.01
) -> dict[str, object]:
    return {
        "id": id_,
        "time": time_,
        "type": "A",
        "status": status,
        "domain": domain,
        "list_id": -4 if status == "GRAVITY" else None,
        "client": {"ip": client_ip, "name": None},
        "reply": {"type": "IP", "time": latency},
    }


def _provider(fake: FakePihole, **kwargs: object) -> PiholeV6Provider:
    client = httpx.Client(
        base_url="http://pihole.test", transport=httpx.MockTransport(fake.handler())
    )
    return PiholeV6Provider(
        base_url="http://pihole.test",
        password=fake.password,
        client=client,
        now=lambda: FIXED_NOW,
        **kwargs,  # type: ignore[arg-type]
    )


# --------------------------------------------------------------------------------- authentication


def test_authenticates_once_and_reuses_the_session() -> None:
    fake = FakePihole()
    provider = _provider(fake)
    provider.health()
    provider.get_summary()
    provider.get_summary()
    assert fake.auth_calls == 1


def test_wrong_password_raises_authentication_error() -> None:
    fake = FakePihole()
    provider = PiholeV6Provider(
        base_url="http://pihole.test",
        password="wrong-guess",
        client=httpx.Client(
            base_url="http://pihole.test", transport=httpx.MockTransport(fake.handler())
        ),
        now=lambda: FIXED_NOW,
    )
    with pytest.raises(AuthenticationError):
        provider.get_summary()


def test_expired_session_triggers_reauthentication() -> None:
    fake = FakePihole()
    fake.session_validity = 10  # below the 30s safety margin: expires immediately
    provider = _provider(fake)
    provider.get_summary()
    assert fake.auth_calls == 1
    provider.get_summary()
    assert fake.auth_calls == 2  # max(validity(10) - margin(30), 0) == 0: expires immediately


def test_401_on_a_data_call_triggers_one_reauth_and_retry() -> None:
    fake = FakePihole()
    provider = _provider(fake)
    provider.get_summary()
    assert fake.auth_calls == 1
    fake.valid_sids.clear()  # simulate FTL restarting and invalidating the session
    summary = provider.get_summary()
    assert summary.total_queries == 100
    assert fake.auth_calls == 2


def test_repeated_401_raises_authentication_error() -> None:
    fake = FakePihole()

    def always_unauthorized(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/auth":
            return fake.handler()(request)
        return httpx.Response(401, json={"error": {"key": "unauthorized"}})

    provider = PiholeV6Provider(
        base_url="http://pihole.test",
        password=fake.password,
        client=httpx.Client(
            base_url="http://pihole.test", transport=httpx.MockTransport(always_unauthorized)
        ),
        now=lambda: FIXED_NOW,
    )
    with pytest.raises(AuthenticationError):
        provider.get_summary()


# ------------------------------------------------------------------------------------- transport


def test_timeout_raises_provider_unavailable() -> None:
    fake = FakePihole()
    fake.force_timeout_paths.add("/api/stats/summary")
    provider = _provider(fake)
    with pytest.raises(ProviderUnavailableError):
        provider.get_summary()


def test_connection_error_raises_provider_unavailable() -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    provider = PiholeV6Provider(
        base_url="http://pihole.test",
        password=GOOD_PASSWORD,
        client=httpx.Client(base_url="http://pihole.test", transport=httpx.MockTransport(broken)),
        now=lambda: FIXED_NOW,
    )
    with pytest.raises(ProviderUnavailableError):
        provider.get_summary()


def test_server_error_raises_provider_unavailable() -> None:
    fake = FakePihole()
    fake.force_500_paths.add("/api/stats/summary")
    provider = _provider(fake)
    with pytest.raises(ProviderUnavailableError):
        provider.get_summary()


def test_malformed_summary_raises_malformed_response_error() -> None:
    fake = FakePihole()
    fake.summary = {"unexpected": "shape"}
    provider = _provider(fake)
    with pytest.raises(MalformedResponseError):
        provider.get_summary()


# ---------------------------------------------------------------------------------------- health


def test_health_ok_when_reachable() -> None:
    provider = _provider(FakePihole())
    health = provider.health()
    assert health.status is HealthStatus.OK


def test_health_down_when_unreachable() -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    provider = PiholeV6Provider(
        base_url="http://pihole.test",
        password=GOOD_PASSWORD,
        client=httpx.Client(base_url="http://pihole.test", transport=httpx.MockTransport(broken)),
        now=lambda: FIXED_NOW,
    )
    health = provider.health()
    assert health.status is HealthStatus.DOWN


def test_health_down_on_bad_password() -> None:
    fake = FakePihole()
    provider = PiholeV6Provider(
        base_url="http://pihole.test",
        password="wrong",
        client=httpx.Client(
            base_url="http://pihole.test", transport=httpx.MockTransport(fake.handler())
        ),
        now=lambda: FIXED_NOW,
    )
    health = provider.health()
    assert health.status is HealthStatus.DOWN


# --------------------------------------------------------------------------------------- summary


def test_get_summary_maps_real_fields() -> None:
    provider = _provider(FakePihole())
    summary = provider.get_summary()
    assert summary.total_queries == 100
    assert summary.blocked_queries == 10
    assert summary.cached_queries == 50  # CACHE + CACHE_STALE
    assert summary.unique_clients == 2
    assert summary.collected_at == FIXED_NOW


# --------------------------------------------------------------------------------------- clients


def test_list_clients_maps_network_devices() -> None:
    fake = FakePihole()
    fake.devices = [
        {
            "hwaddr": "AA:BB:CC:DD:EE:FF",
            "firstSeen": 1000,
            "lastQuery": 2000,
            "numQueries": 5,
            "ips": [{"ip": "192.168.1.50", "name": "laptop"}],
        },
        {
            "hwaddr": "ip-192.168.1.121",  # Pi-hole's synthetic non-MAC placeholder
            "firstSeen": 1000,
            "lastQuery": 1000,
            "numQueries": 0,
            "ips": [{"ip": "192.168.1.121", "name": "pi.hole"}],
        },
    ]
    fake.queries = [
        _query(1, client_ip="192.168.1.50", domain="ads.example", status="GRAVITY", time_=1500),
    ]
    provider = _provider(fake)
    clients = provider.list_clients()
    assert len(clients) == 2
    real_mac = next(c for c in clients if c.mac == "aa:bb:cc:dd:ee:ff")
    assert real_mac.hostname == "laptop"
    assert real_mac.ipv4_addresses == (IPv4Address("192.168.1.50"),)
    assert real_mac.total_queries == 5
    assert real_mac.blocked_queries == 1
    synthetic = next(c for c in clients if c.mac is None)
    assert synthetic.client_id == "192.168.1.121"  # falls back to the address, not the fake mac


def test_list_clients_orders_by_client_id() -> None:
    fake = FakePihole()
    fake.devices = [
        {
            "hwaddr": None,
            "firstSeen": 1,
            "lastQuery": 1,
            "numQueries": 0,
            "ips": [{"ip": "192.168.1.9", "name": None}],
        },
        {
            "hwaddr": None,
            "firstSeen": 1,
            "lastQuery": 1,
            "numQueries": 0,
            "ips": [{"ip": "192.168.1.2", "name": None}],
        },
    ]
    provider = _provider(fake)
    clients = provider.list_clients()
    assert [c.client_id for c in clients] == sorted(c.client_id for c in clients)


# ------------------------------------------------------------------------------------- query log

WINDOW = QueryFilter(since=FIXED_NOW - timedelta(minutes=30), until=FIXED_NOW)


def test_query_log_empty_returns_no_cursor() -> None:
    provider = _provider(FakePihole())
    page = provider.query_log(WINDOW)
    assert page.entries == ()
    assert page.next_cursor is None


def test_query_log_maps_status_to_outcome_and_latency() -> None:
    fake = FakePihole()
    base = (FIXED_NOW - timedelta(minutes=1)).timestamp()
    fake.queries = [
        _query(
            3,
            client_ip="192.168.1.50",
            domain="a.example",
            status="FORWARDED",
            time_=base,
            latency=0.05,
        ),
        _query(2, client_ip="192.168.1.50", domain="b.example", status="CACHE", time_=base - 1),
        _query(1, client_ip="192.168.1.50", domain="ads.example", status="GRAVITY", time_=base - 2),
    ]
    provider = _provider(fake)
    page = provider.query_log(WINDOW, limit=10)
    outcomes = {e.domain: e.outcome for e in page.entries}
    assert outcomes["a.example"] is QueryOutcome.FORWARDED
    assert outcomes["b.example"] is QueryOutcome.CACHED
    assert outcomes["ads.example"] is QueryOutcome.BLOCKED
    blocked_entry = next(e for e in page.entries if e.domain == "ads.example")
    assert blocked_entry.blocked_by is not None
    forwarded_entry = next(e for e in page.entries if e.domain == "a.example")
    assert forwarded_entry.blocked_by is None
    assert forwarded_entry.latency_ms == 50.0


def test_query_log_pagination_is_complete_and_stable() -> None:
    fake = FakePihole()
    base = (FIXED_NOW - timedelta(minutes=29)).timestamp()
    fake.queries = [
        _query(
            i, client_ip="192.168.1.50", domain=f"d{i}.example", status="FORWARDED", time_=base + i
        )
        for i in range(1, 51)
    ][::-1]  # newest (highest id/time) first, matching real Pi-hole ordering
    provider = _provider(fake)

    def _all(limit: int) -> list[object]:
        entries: list[object] = []
        cursor = None
        while True:
            page = provider.query_log(WINDOW, limit=limit, cursor=cursor)
            entries.extend(page.entries)
            if page.next_cursor is None:
                return entries
            cursor = page.next_cursor

    whole = _all(1000)
    paged = _all(7)
    assert whole == paged
    assert len(whole) == 50


def test_query_log_client_side_outcome_filter_does_not_lose_pagination_correctness() -> None:
    fake = FakePihole()
    base = (FIXED_NOW - timedelta(minutes=29)).timestamp()
    statuses = ["GRAVITY", "FORWARDED", "CACHE"]
    fake.queries = [
        _query(
            i,
            client_ip="192.168.1.50",
            domain=f"d{i}.example",
            status=statuses[i % 3],
            time_=base + i,
        )
        for i in range(1, 31)
    ][::-1]
    provider = _provider(fake)

    def _all_blocked(limit: int) -> list[object]:
        entries: list[object] = []
        cursor = None
        blocked_filter = WINDOW.model_copy(update={"outcome": QueryOutcome.BLOCKED})
        while True:
            page = provider.query_log(blocked_filter, limit=limit, cursor=cursor)
            entries.extend(page.entries)
            if page.next_cursor is None:
                return entries
            cursor = page.next_cursor

    whole = _all_blocked(1000)
    paged = _all_blocked(2)
    assert whole == paged
    assert all(e.outcome is QueryOutcome.BLOCKED for e in whole)  # type: ignore[attr-defined]
    assert len(whole) == 10


def test_query_log_large_page_spans_multiple_http_requests() -> None:
    fake = FakePihole()
    base = (FIXED_NOW - timedelta(minutes=29)).timestamp()
    fake.queries = [
        _query(
            i,
            client_ip="192.168.1.50",
            domain=f"d{i}.example",
            status="FORWARDED",
            time_=base + i / 3000,
        )
        for i in range(1, 2501)
    ][::-1]
    provider = _provider(fake)
    page = provider.query_log(WINDOW, limit=1000)
    assert len(page.entries) == 1000
    assert page.next_cursor == "1000"


def test_query_log_rejects_bad_limit() -> None:
    provider = _provider(FakePihole())
    with pytest.raises(ValueError, match="limit"):
        provider.query_log(WINDOW, limit=0)
    with pytest.raises(ValueError, match="limit"):
        provider.query_log(WINDOW, limit=1001)


def test_query_log_rejects_malformed_cursor() -> None:
    provider = _provider(FakePihole())
    with pytest.raises(ValueError, match="cursor"):
        provider.query_log(WINDOW, cursor="not-a-cursor")


# ---------------------------------------------------------------------------------- system metrics


def test_system_metrics_maps_real_fields() -> None:
    provider = _provider(FakePihole())
    metrics = provider.system_metrics()
    assert metrics.uptime_seconds == 34002
    assert metrics.memory_total_bytes == 3886900 * 1024
    assert metrics.memory_used_bytes == 151344 * 1024
    assert metrics.temperature_celsius == 41.4
    assert metrics.collected_at == FIXED_NOW


def test_system_metrics_temperature_none_when_sensors_unavailable() -> None:
    fake = FakePihole()
    fake.sensors = None
    provider = _provider(fake)
    metrics = provider.system_metrics()
    assert metrics.temperature_celsius is None


def test_system_metrics_malformed_raises() -> None:
    fake = FakePihole()
    fake.system = {"system": {}}
    provider = _provider(fake)
    with pytest.raises(MalformedResponseError):
        provider.system_metrics()


# --------------------------------------------------------------------------------- domain lookup


def test_lookup_domain_maps_gravity_match_to_source_id() -> None:
    fake = FakePihole()
    fake.search_results["blocked.example"] = {
        "search": {
            "domains": [],
            "gravity": [
                {
                    "type": "block",
                    "enabled": True,
                    "address": "https://example.test/pro.txt",
                }
            ],
        }
    }
    provider = _provider(fake, source_urls={"hagezi-multi-pro": "https://example.test/pro.txt"})
    result = provider.lookup_domain("blocked.example")
    assert result.blocked is True
    assert result.matched_sources == ("hagezi-multi-pro",)


def test_lookup_domain_not_blocked() -> None:
    provider = _provider(FakePihole())
    result = provider.lookup_domain("clean.example")
    assert result.blocked is False
    assert result.matched_sources == ()


# -------------------------------------------------------------------------- blocklist deployment

ENTRIES = frozenset(
    {BlockEntry("ads.contract.example", True), BlockEntry("track.contract.example", False)}
)


def test_deploy_blocklist_dry_run_makes_no_domain_api_calls() -> None:
    fake = FakePihole()
    provider = _provider(fake)
    result = provider.deploy_blocklist("contract-list", ENTRIES, dry_run=True)
    assert result.dry_run is True
    assert result.applied is False
    assert fake.deny_domains == []


def test_deploy_blocklist_applies_exact_and_regex_entries() -> None:
    fake = FakePihole()
    provider = _provider(fake)
    result = provider.deploy_blocklist("contract-list", ENTRIES, dry_run=False)
    assert result.applied is True
    domains = {d["domain"] for d in fake.deny_domains}
    assert "track.contract.example" in domains  # exact
    assert any("ads\\.contract\\.example" in d for d in domains)  # regex form (escaped)


def test_deploy_blocklist_redeployment_replaces_previous_entries() -> None:
    fake = FakePihole()
    provider = _provider(fake)
    provider.deploy_blocklist("contract-list", ENTRIES, dry_run=False)
    provider.deploy_blocklist(
        "contract-list", frozenset({BlockEntry("new.contract.example", False)}), dry_run=False
    )
    domains = {d["domain"] for d in fake.deny_domains}
    assert domains == {"new.contract.example"}


def test_deploy_blocklist_rejects_oversized_entry_sets() -> None:
    from home_dns.providers.base import ProviderError

    fake = FakePihole()
    provider = _provider(fake)
    huge = frozenset(BlockEntry(f"d{i}.example", False) for i in range(5001))
    with pytest.raises(ProviderError, match="safety cap"):
        provider.deploy_blocklist("huge-list", huge, dry_run=False)
    assert fake.deny_domains == []
