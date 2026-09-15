"""Dashboard API: role matrix, sessions, CSRF, lockout, views and data exposure (a7 spec §7-§9)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from home_dns.api.app import create_app
from home_dns.api.context import CollectorRunner, DashboardContext, MaintenanceStatus
from home_dns.api.views import build_config_view
from home_dns.collector import Collector
from home_dns.config.filtering import load_filtering_config
from home_dns.config.loader import load_config
from home_dns.config.settings import Environment
from home_dns.config.storage import load_storage_config
from home_dns.core.anomaly import Anomaly, AnomalySignal
from home_dns.core.auth import Role, ScryptParams, hash_password
from home_dns.core.models import QueryFilter, QueryPage
from home_dns.core.monitoring import Incident, IncidentState
from home_dns.core.storage import DiskUsage
from home_dns.providers.base import ProviderUnavailableError
from home_dns.providers.mock import MockDnsProvider
from home_dns.storage.dashboard import DashboardStore

FAST = ScryptParams(n=2**10, r=8, p=1)
ROME = ZoneInfo("Europe/Rome")
T0 = datetime(2026, 9, 13, 10, 0, tzinfo=UTC)
ADMIN_PW = "admin password 123"
VIEWER_PW = "viewer password 123"
LAST_BACKUP = datetime(2026, 9, 13, 3, 0, tzinfo=UTC)


class Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now


class SwitchableProvider(MockDnsProvider):
    down = False

    def query_log(
        self, query: QueryFilter, *, limit: int = 100, cursor: str | None = None
    ) -> QueryPage:
        if self.down:
            raise ProviderUnavailableError("http://internal-secret-host:8080 unreachable")
        return super().query_log(query, limit=limit, cursor=cursor)

    def system_metrics(self):  # type: ignore[no-untyped-def]
        if self.down:
            raise ProviderUnavailableError("down")
        return super().system_metrics()


class Env:
    def __init__(self, tmp_path: Path, repo_config_dir: Path, *, collector: bool = False) -> None:
        self.clock = Clock(T0)
        self.store = DashboardStore.open(tmp_path)
        self.store.set_user("admin", Role.ADMIN, hash_password(ADMIN_PW, params=FAST), now=T0)
        self.store.set_user("viewer", Role.VIEWER, hash_password(VIEWER_PW, params=FAST), now=T0)
        self.provider = SwitchableProvider(now=self.clock)
        self.collector = Collector(self.provider, self.store, tz=ROME, now=self.clock)
        settings = load_config(
            environment=Environment.DEVELOPMENT, config_dir=repo_config_dir
        ).settings
        filtering = load_filtering_config(repo_config_dir, now=T0).config
        storage = load_storage_config(repo_config_dir)
        self.context = DashboardContext(
            store=self.store,
            filtering=filtering,
            config_view=build_config_view(
                settings, filtering, storage.thresholds, storage.retention
            ),
            status=lambda: MaintenanceStatus(
                last_backup_at=LAST_BACKUP,
                incidents=(
                    Incident("dns_down", IncidentState.INCIDENT, opened_at=T0),
                    Incident("storage", IncidentState.OK),
                ),
            ),
            tz=ROME,
            now=self.clock,
            password_params=FAST,
            collector=CollectorRunner(self.collector, 0.01, 0.01) if collector else None,
        )
        self.app = create_app(
            environment=Environment.DEVELOPMENT, provider=self.provider, dashboard=self.context
        )

    def populate(self, minutes: int = 30) -> None:
        self.collector.poll()
        self.clock.now += timedelta(minutes=minutes)
        self.collector.poll()
        self.collector.flush()

    def client(self) -> TestClient:
        return TestClient(self.app, base_url="https://testserver")

    def login(self, username: str = "admin", password: str = ADMIN_PW) -> tuple[TestClient, str]:
        client = self.client()
        response = client.post(
            "/api/v1/auth/login", json={"username": username, "password": password}
        )
        assert response.status_code == 200, response.text
        return client, response.json()["csrf_token"]


@pytest.fixture
def env(tmp_path: Path, repo_config_dir: Path) -> Iterator[Env]:
    environment = Env(tmp_path, repo_config_dir)
    environment.populate()
    yield environment
    environment.store.close()


VIEWER_ROUTES = [
    "/api/v1/auth/session",
    "/api/v1/overview",
    "/api/v1/devices",
    "/api/v1/devices/1",
    "/api/v1/metrics/history",
    "/api/v1/alerts",
    "/api/v1/incidents/history",
    "/api/v1/config",
    "/api/v1/anomalies",
    "/api/v1/devices/1/anomalies",
]
ADMIN_ROUTES = ["/api/v1/devices/1/activity", "/api/v1/queries"]


# ------------------------------------------------------------------------ access control


@pytest.mark.parametrize("path", VIEWER_ROUTES + ADMIN_ROUTES)
def test_every_dashboard_route_requires_a_session(env: Env, path: str) -> None:
    assert env.client().get(path).status_code == 401


def test_patch_and_logout_require_a_session(env: Env) -> None:
    client = env.client()
    assert client.patch("/api/v1/devices/1", json={"custom_name": "x"}).status_code == 401
    assert client.post("/api/v1/auth/logout").status_code == 401


@pytest.mark.parametrize("path", VIEWER_ROUTES)
def test_viewer_can_read_aggregated_views(env: Env, path: str) -> None:
    client, _ = env.login("viewer", VIEWER_PW)
    assert client.get(path).status_code == 200


@pytest.mark.parametrize("path", ADMIN_ROUTES)
def test_viewer_cannot_read_domain_level_data(env: Env, path: str) -> None:
    client, _ = env.login("viewer", VIEWER_PW)
    assert client.get(path).status_code == 403


def test_viewer_cannot_modify_devices(env: Env) -> None:
    client, csrf = env.login("viewer", VIEWER_PW)
    response = client.patch(
        "/api/v1/devices/1", json={"custom_name": "x"}, headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 403


@pytest.mark.parametrize("path", VIEWER_ROUTES + ADMIN_ROUTES)
def test_admin_can_read_everything(env: Env, path: str) -> None:
    client, _ = env.login()
    assert client.get(path).status_code == 200


def test_health_stays_public_and_dashboard_is_absent_without_context() -> None:
    client = TestClient(create_app(environment=Environment.DEVELOPMENT, provider=MockDnsProvider()))
    assert client.get("/api/v1/health").status_code == 200
    assert (
        client.post("/api/v1/auth/login", json={"username": "a", "password": "b"}).status_code
        == 404
    )


# -------------------------------------------------------------------------------- login


def test_login_sets_a_hardened_cookie(env: Env) -> None:
    response = env.client().post(
        "/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PW}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "admin" and body["role"] == "admin" and len(body["csrf_token"]) >= 43
    cookie = response.headers["set-cookie"].lower()
    for flag in ("hd_session=", "httponly", "samesite=strict", "secure", "path=/api"):
        assert flag in cookie


def test_cookie_secure_can_be_disabled_for_loopback_development(env: Env) -> None:
    env.context.cookie_secure = False
    response = env.client().post(
        "/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PW}
    )
    assert "secure" not in response.headers["set-cookie"].lower()


def test_wrong_password_and_unknown_user_are_indistinguishable(env: Env) -> None:
    client = env.client()
    wrong = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "nope nope nope"}
    )
    unknown = client.post(
        "/api/v1/auth/login", json={"username": "ghost", "password": "nope nope nope"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert "set-cookie" not in wrong.headers


def test_five_failures_lock_the_username_even_with_the_right_password(env: Env) -> None:
    client = env.client()
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"username": "admin", "password": "bad password!!"})
    locked = client.post("/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PW})
    assert locked.status_code == 429
    env.clock.now += timedelta(minutes=16)
    env.context.limiter.reset("ip:testclient")
    assert (
        client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PW}
        ).status_code
        == 200
    )


def test_failures_from_one_address_lock_that_address_for_every_username(env: Env) -> None:
    client = env.client()
    for name in ("a", "b", "c", "d", "e"):
        client.post("/api/v1/auth/login", json={"username": name, "password": "bad password!!"})
    assert (
        client.post(
            "/api/v1/auth/login", json={"username": "viewer", "password": VIEWER_PW}
        ).status_code
        == 429
    )


def test_login_payload_is_validated(env: Env) -> None:
    assert env.client().post("/api/v1/auth/login", json={"username": ""}).status_code == 422


# ----------------------------------------------------------------------- session, CSRF


def test_unsafe_methods_require_the_session_csrf_token(env: Env) -> None:
    client, csrf = env.login()
    body = {"custom_name": "PC Studio"}
    assert client.patch("/api/v1/devices/1", json=body).status_code == 403
    assert (
        client.patch("/api/v1/devices/1", json=body, headers={"X-CSRF-Token": "x" * 43}).status_code
        == 403
    )
    assert (
        client.patch("/api/v1/devices/1", json=body, headers={"X-CSRF-Token": csrf}).status_code
        == 200
    )
    assert client.post("/api/v1/auth/logout").status_code == 403


def test_logout_revokes_the_session(env: Env) -> None:
    client, csrf = env.login()
    assert client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert client.get("/api/v1/auth/session").status_code == 401


def test_session_expires_after_idle_timeout(env: Env) -> None:
    client, _ = env.login()
    env.clock.now += timedelta(hours=11)
    assert client.get("/api/v1/auth/session").status_code == 200  # also refreshes last_seen
    env.clock.now += timedelta(hours=11)
    assert client.get("/api/v1/auth/session").status_code == 200
    env.clock.now += timedelta(hours=12)
    assert client.get("/api/v1/auth/session").status_code == 401


def test_session_expires_after_absolute_lifetime_despite_activity(env: Env) -> None:
    client, _ = env.login()
    for _ in range(16):  # 176 h > 168 h absolute lifetime
        env.clock.now += timedelta(hours=11)
        client.get("/api/v1/auth/session")
    assert client.get("/api/v1/auth/session").status_code == 401


def test_session_writes_are_throttled(env: Env) -> None:
    from home_dns.core.auth import token_digest

    client, _ = env.login()
    digest = token_digest(client.cookies["hd_session"])

    def last_seen() -> datetime:
        session = env.store.get_session(digest)
        assert session is not None
        return session.last_seen_at

    before = last_seen()
    env.clock.now += timedelta(minutes=4)
    client.get("/api/v1/auth/session")
    assert last_seen() == before
    env.clock.now += timedelta(minutes=2)
    client.get("/api/v1/auth/session")
    assert last_seen() == env.clock.now


def test_password_change_revokes_existing_sessions(env: Env) -> None:
    client, _ = env.login()
    env.store.set_user(
        "admin", Role.ADMIN, hash_password("a brand new password", params=FAST), now=T0
    )
    assert client.get("/api/v1/auth/session").status_code == 401


# -------------------------------------------------------------------------------- views


def test_overview_reports_totals_system_and_maintenance(env: Env) -> None:
    client, _ = env.login("viewer", VIEWER_PW)
    body = client.get("/api/v1/overview").json()
    assert body["provider"] == {"name": "mock", "status": "ok"}
    counters = body["last_24h"]
    assert counters["total"] > 0 and counters["allowed"] == counters["total"] - counters["blocked"]
    assert 0 < counters["block_percentage"] < 100
    assert counters["latency_p50_ms"] is not None and counters["cache_hit_ratio"] is not None
    assert set(counters["blocked_by_source"]) <= {"hagezi-multi-pro", "hagezi-tif-mini"}
    assert body["queries_per_second"] > 0
    assert body["system"]["memory_total_bytes"] > 0
    assert body["open_incidents"] == 1
    assert body["last_backup_at"] == "2026-09-13T03:00:00Z"
    assert body["metrics_as_of"] == "2026-09-13T10:30:00Z"


def test_overview_degrades_when_provider_is_down(env: Env) -> None:
    client, _ = env.login()
    env.provider.down = True
    body = client.get("/api/v1/overview").json()
    assert body["system"] is None
    assert body["last_24h"]["total"] > 0  # history comes from local rollups


def test_devices_list_and_detail(env: Env) -> None:
    client, _ = env.login("viewer", VIEWER_PW)
    devices = client.get("/api/v1/devices").json()
    assert len(devices) == 16
    first = devices[0]
    assert first["group_id"] == "DEFAULT" and first["name"] == first["hostname"]
    assert first["mac"].startswith("00:00:5e:00:53:")
    assert (
        sum(d["last_24h"]["total"] for d in devices)
        == client.get("/api/v1/overview").json()["last_24h"]["total"]
    )
    assert client.get(f"/api/v1/devices/{first['device_id']}").json() == first
    assert client.get("/api/v1/devices/999").status_code == 404


def test_admin_renames_and_regroups_a_device(env: Env) -> None:
    client, csrf = env.login()
    headers = {"X-CSRF-Token": csrf}
    updated = client.patch(
        "/api/v1/devices/1",
        json={"custom_name": "  PC Studio ", "group_id": "GAMING"},
        headers=headers,
    ).json()
    assert (updated["custom_name"], updated["name"], updated["group_id"]) == (
        "PC Studio",
        "PC Studio",
        "GAMING",
    )
    cleared = client.patch("/api/v1/devices/1", json={"custom_name": ""}, headers=headers).json()
    assert cleared["custom_name"] is None and cleared["group_id"] == "GAMING"
    assert (
        client.patch("/api/v1/devices/1", json={"group_id": "NOPE"}, headers=headers).status_code
        == 422
    )
    assert (
        client.patch(
            "/api/v1/devices/1", json={"custom_name": "x" * 65}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.patch("/api/v1/devices/999", json={"custom_name": "x"}, headers=headers).status_code
        == 404
    )
    env.populate(5)  # the collector must not overwrite user-owned fields
    assert client.get("/api/v1/devices/1").json()["custom_name"] is None
    assert client.get("/api/v1/devices/1").json()["group_id"] == "GAMING"


def test_device_activity_shows_domains(env: Env) -> None:
    client, _ = env.login()
    body = client.get("/api/v1/devices/1/activity").json()
    assert body["top_domains"] and body["recent"]
    # The mock logs ~2000 queries per device per day, so the 2000-entry scan cap is reached.
    assert body["truncated"] is True and len(body["recent"]) == 50
    times = [e["time"] for e in body["recent"]]
    assert times == sorted(times, reverse=True)
    assert all(d["domain"].endswith(".example") for d in body["top_domains"] + body["top_blocked"])


def test_device_activity_reports_truncation(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    import home_dns.api.views as views

    monkeypatch.setattr(views, "_ACTIVITY_MAX_ENTRIES", 5)
    client, _ = env.login()
    body = client.get("/api/v1/devices/1/activity").json()
    assert body["truncated"] is True and len(body["recent"]) == 5


def test_provider_outage_is_503_without_leaking_details(env: Env) -> None:
    client, _ = env.login()
    env.provider.down = True
    for path in ("/api/v1/devices/1/activity", "/api/v1/queries"):
        response = client.get(path)
        assert response.status_code == 503
        assert "internal-secret-host" not in response.text


def test_history_matches_overview_and_validates_windows(env: Env) -> None:
    client, _ = env.login("viewer", VIEWER_PW)
    total = client.get("/api/v1/overview").json()["last_24h"]["total"]
    hourly = client.get("/api/v1/metrics/history", params={"resolution": "hour"}).json()
    assert sum(p["counters"]["total"] for p in hourly["points"]) == total
    minute = client.get("/api/v1/metrics/history", params={"resolution": "minute"}).json()
    assert sum(p["counters"]["total"] for p in minute["points"]) == total
    assert all(p["queries_per_second"] > 0 for p in minute["points"])
    day = client.get("/api/v1/metrics/history", params={"resolution": "day"}).json()
    [point] = day["points"]
    assert point["bucket_start"] == "2026-09-12T22:00:00Z"  # local midnight in Rome
    one = client.get(
        "/api/v1/metrics/history", params={"resolution": "hour", "device_id": 1}
    ).json()
    assert 0 < sum(p["counters"]["total"] for p in one["points"]) < total
    bad = [
        {"resolution": "minute", "since": "2026-09-01T00:00:00Z", "until": "2026-09-13T00:00:00Z"},
        {"since": "2026-09-13T10:00:00Z", "until": "2026-09-13T09:00:00Z"},
        {"since": "2026-09-13T08:00:00"},
        {"resolution": "week"},
    ]
    for params in bad:
        assert client.get("/api/v1/metrics/history", params=params).status_code == 422, params


def test_queries_proxy_filters_and_validates(env: Env) -> None:
    client, _ = env.login()
    page = client.get("/api/v1/queries", params={"outcome": "blocked", "limit": 5}).json()
    assert len(page["entries"]) == 5 and page["next_cursor"]
    assert all(e["outcome"] == "blocked" and e["blocked_by"] for e in page["entries"])
    following = client.get(
        "/api/v1/queries", params={"outcome": "blocked", "limit": 5, "cursor": page["next_cursor"]}
    ).json()
    assert {e["id"] for e in following["entries"]}.isdisjoint(e["id"] for e in page["entries"])
    for params in (
        {"cursor": "garbage"},
        {"limit": 0},
        {"client": "not-an-ip"},
        {"since": "2026-09-13T11:00:00Z", "until": "2026-09-13T10:00:00Z"},
    ):
        assert client.get("/api/v1/queries", params=params).status_code == 422, params


def test_alerts_lists_only_open_incidents(env: Env) -> None:
    client, _ = env.login("viewer", VIEWER_PW)
    assert [a["check_name"] for a in client.get("/api/v1/alerts").json()] == ["dns_down"]


def test_config_view_is_an_allowlist(env: Env) -> None:
    client, _ = env.login("viewer", VIEWER_PW)
    body = client.get("/api/v1/config").json()
    assert body["dns_provider"] == "mock"
    assert {g["id"] for g in body["groups"]} >= {"DEFAULT", "SMART-TV", "XBOX"}
    assert body["metrics"]["hour_retention_days"] == 30
    assert set(body) == {
        "dns_provider",
        "notifier",
        "groups",
        "policies",
        "blocklist_sources",
        "storage",
        "metrics",
    }
    assert set(body["blocklist_sources"][0]) == {
        "id",
        "name",
        "categories",
        "update_interval_hours",
        "last_activated_at",
    }


def test_overview_includes_live_storage_usage(env: Env) -> None:
    env.context.disk_usage = lambda: DiskUsage(
        total_bytes=1_000_000, used_bytes=850_000, free_bytes=150_000
    )
    client, _ = env.login("viewer", VIEWER_PW)
    storage = client.get("/api/v1/overview").json()["storage"]
    assert storage["total_bytes"] == 1_000_000
    assert storage["used_bytes"] == 850_000
    assert storage["used_percent"] == 85.0


def test_overview_defaults_storage_to_zero_when_unwired(env: Env) -> None:
    # Env never overrides disk_usage, so this exercises DashboardContext's own zero default —
    # it never lies about real usage when no provider is wired in.
    client, _ = env.login("viewer", VIEWER_PW)
    storage = client.get("/api/v1/overview").json()["storage"]
    assert storage == {"total_bytes": 0, "used_bytes": 0, "free_bytes": 0, "used_percent": 0.0}


def test_config_exposes_per_source_blocklist_freshness(env: Env) -> None:
    when = datetime(2026, 9, 13, 4, 0, tzinfo=UTC)
    env.context.blocklist_freshness = lambda: {"hagezi-multi-pro": when}
    client, _ = env.login("viewer", VIEWER_PW)
    config_body = client.get("/api/v1/config").json()
    sources = {s["id"]: s["last_activated_at"] for s in config_body["blocklist_sources"]}
    assert sources["hagezi-multi-pro"] == "2026-09-13T04:00:00Z"
    assert sources["hagezi-tif-mini"] is None  # not in the freshness map: honestly unknown


def test_incident_history_lists_persisted_transitions(env: Env) -> None:
    t1 = datetime(2026, 9, 13, 4, 0, tzinfo=UTC)
    t2 = datetime(2026, 9, 13, 5, 0, tzinfo=UTC)
    env.store.record_incident_event("storage", "opened", occurred_at=t1, severity="warning")
    env.store.record_incident_event("storage", "recovered", occurred_at=t2, severity=None)
    client, _ = env.login("viewer", VIEWER_PW)
    body = client.get("/api/v1/incidents/history").json()
    assert [(e["transition"], e["severity"]) for e in body] == [
        ("recovered", None),
        ("opened", "warning"),
    ]
    assert "notified" not in body[0]  # not tracked anywhere in this codebase yet — never fabricated

    limited = client.get("/api/v1/incidents/history", params={"limit": 1}).json()
    assert len(limited) == 1


def test_anomalies_list_is_empty_with_no_detections(env: Env) -> None:
    client, _ = env.login("viewer", VIEWER_PW)
    assert client.get("/api/v1/anomalies").json() == []


def test_anomalies_round_trip_through_the_api(env: Env) -> None:
    from home_dns.storage.dashboard import DeviceUpsert, FlushBatch

    env.store.flush(
        FlushBatch(watermark=T0, devices=(DeviceUpsert(1, None, "tv-01.example", T0, T0),))
    )
    env.store.flush(
        FlushBatch(
            watermark=T0,
            anomalies=(
                Anomaly(
                    device_id=1,
                    detected_at=T0,
                    signals=(AnomalySignal.NXDOMAIN_BURST, AnomalySignal.BEACONING),
                    score=50,
                    severity="medium",
                    reason="NXDOMAIN rate and regular repeated-domain interval significantly "
                    "exceed this device's recent baseline",
                ),
            ),
        )
    )
    client, _ = env.login("viewer", VIEWER_PW)

    listed = client.get("/api/v1/anomalies").json()
    assert len(listed) == 1
    entry = listed[0]
    assert entry["device_id"] == 1
    assert entry["severity"] == "medium"
    assert entry["score"] == 50
    assert set(entry["signals"]) == {"nxdomain_burst", "beaconing"}
    assert "significantly exceed" in entry["reason"]

    by_id = client.get(f"/api/v1/anomalies/{entry['id']}").json()
    assert by_id == entry

    by_device = client.get("/api/v1/devices/1/anomalies").json()
    assert by_device == listed


def test_anomaly_by_id_404_when_missing(env: Env) -> None:
    client, _ = env.login("viewer", VIEWER_PW)
    assert client.get("/api/v1/anomalies/999").status_code == 404


def test_anomalies_for_unknown_device_404(env: Env) -> None:
    client, _ = env.login("viewer", VIEWER_PW)
    assert client.get("/api/v1/devices/999/anomalies").status_code == 404


def test_no_response_contains_secrets(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME_DNS_PIHOLE_APP_PASSWORD", "pihole-secret-value")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:telegram-secret-value")
    client, csrf = env.login()
    session_token = client.cookies["hd_session"]
    bodies = [client.get(path).text for path in VIEWER_ROUTES + ADMIN_ROUTES]
    bodies.append(
        client.patch(
            "/api/v1/devices/1", json={"custom_name": "x"}, headers={"X-CSRF-Token": csrf}
        ).text
    )
    for text in bodies:
        for forbidden in (
            "scrypt$",
            session_token,
            ADMIN_PW,
            "password_hash",
            "secret-value",
            "token_digest",
        ):
            assert forbidden not in text


def test_security_headers(env: Env) -> None:
    client, _ = env.login()
    for path in ("/api/v1/health", "/api/v1/overview"):
        headers = client.get(path).headers
        assert headers["cache-control"] == "no-store"
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["x-frame-options"] == "DENY"
        assert headers["referrer-policy"] == "no-referrer"
        assert "default-src 'none'" in headers["content-security-policy"]


# ------------------------------------------------------------------------------ lifespan


def test_lifespan_runs_the_collector_and_flushes_on_shutdown(
    tmp_path: Path, repo_config_dir: Path
) -> None:
    environment = Env(tmp_path, repo_config_dir, collector=True)
    with environment.client() as client:
        assert client.get("/api/v1/health").status_code == 200
    assert environment.store.load_watermark() == T0
    environment.store.close()
