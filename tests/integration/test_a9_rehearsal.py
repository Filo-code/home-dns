"""A9 — offline integration rehearsal (docs/implementation-plan.md §A9,
docs/specs/a9-integration-rehearsal.md).

Proves the full offline chain actually connects end to end, through the real CLI entry point
(not just internal functions, which the rest of the suite already covers in isolation):

    blocklist pipeline -> mock DNS provider -> monitoring incidents -> Telegram notifier
    (mock, dry-run) -> dashboard backend -> dashboard API

Nothing here touches a real network, a real Pi, or a real Pi-hole: the fetcher, disk usage and
notifier are all injected fakes, the same pattern tests/unit/test_cli.py already uses. The
network guard in tests/conftest.py would fail this test outright if anything tried a real socket.
Uses cli._dashboard_context directly so the dashboard sees exactly the on-disk state `serve`
would build from — including the real incident the monitoring step below creates.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from home_dns import cli
from home_dns.api.app import create_app
from home_dns.collector import Collector
from home_dns.config.filtering import load_filtering_config
from home_dns.config.loader import load_config
from home_dns.config.settings import Environment
from home_dns.config.storage import load_storage_config
from home_dns.core.auth import Role, ScryptParams, hash_password
from home_dns.core.storage import DiskUsage
from home_dns.notify.mock import MockNotifier
from home_dns.pipeline.fetch import FetchResponse
from home_dns.providers.mock import MockDnsProvider
from home_dns.storage.dashboard import DashboardStore
from tests.blocklist_fixtures import ScriptedFetcher, adblock_list, domains
from tests.conftest import DEV_PROFILE

if TYPE_CHECKING:
    from tests.conftest import MakeConfigDir

FIXED_NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
FAST_SCRYPT = ScryptParams(n=2**10, r=8, p=1)
ADMIN_PASSWORD = "rehearsal-admin-pw-12"


class _FakeDisk:
    """Injectable DiskUsageProvider — same pattern as tests/unit/test_cli.py's _FakeDisk."""

    def __init__(self, used_percent: float, total: int = 1_000_000) -> None:
        used = round(total * used_percent / 100)
        self._usage = DiskUsage(total_bytes=total, used_bytes=used, free_bytes=total - used)

    def get(self, path: Path) -> DiskUsage:
        return self._usage


def _run(config_dir: Path, *argv: str, **kwargs: object) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(
        [*argv, "--config-dir", str(config_dir)],
        out=out,
        err=err,
        now=lambda: FIXED_NOW,
        **kwargs,  # type: ignore[arg-type]
    )
    return code, out.getvalue(), err.getvalue()


def test_a9_full_offline_rehearsal(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    data_dir = config_dir.parent / ".local" / "data"

    # ---------------------------------------------------------------- 1. configuration is sound
    code, out, _ = _run(config_dir, "validate-config")
    assert code == 0 and "Result: READY" in out

    # ---------------------------------------------------------------- 2. blocklist pipeline
    code, out, _ = _run(config_dir, "blocklists", "status")
    assert code == 0 and "list-a: current=-" in out  # nothing deployed yet

    fixture_domains = domains(5, prefix="ads")
    fetcher = ScriptedFetcher(
        {
            "https://cdn.example/a.txt": FetchResponse(
                url="https://cdn.example/a.txt",
                status=200,
                content_type="text/plain",
                body=adblock_list(fixture_domains, last_modified=FIXED_NOW).encode("utf-8"),
            ),
        }
    )
    code, out, _ = _run(
        config_dir, "blocklists", "update", "--source", "list-a", "--apply", fetcher=fetcher
    )
    assert code == 0, out
    assert "activated" in out
    assert fetcher.calls == ["https://cdn.example/a.txt"]  # only the scripted, offline URL

    code, out, _ = _run(config_dir, "blocklists", "status")
    assert code == 0 and "list-a: current=" in out and "list-a: current=-" not in out

    # -------------------------------------------------------------------- 3. policy engine
    code, out, _ = _run(
        config_dir, "policy", "explain", "--group", "DEFAULT", "ads0.blocked.example"
    )
    assert code == 0 and "blocked" in out

    # ---------------------------------------------------------------------------- 4. storage safety
    code, _, _ = _run(config_dir, "storage", "status", disk=_FakeDisk(10))
    assert code == 0
    code, _, _ = _run(config_dir, "storage", "backup", "--apply", disk=_FakeDisk(10))
    assert code == 0
    code, out, _ = _run(config_dir, "storage", "verify", disk=_FakeDisk(10))
    assert code == 0 and "invalid" not in out.lower()

    # --------------------------------------------------------- 5. monitoring incidents (real state
    #    machine: incident_after=2 per MONITORING_FILES, so two unhealthy checks are needed)
    _run(config_dir, "monitoring", "status", "--apply", disk=_FakeDisk(95))
    code, out, _ = _run(config_dir, "monitoring", "status", "--apply", disk=_FakeDisk(95))
    assert code == 0 and "incident=incident" in out

    # ------------------------------------------------------------- 6. Telegram notifier (mock, dry
    #    run only — a real send is never attempted in this rehearsal or by this phase's design)
    mock_notifier = MockNotifier()
    code, out, _ = _run(config_dir, "notify", "test", notifier=mock_notifier)
    assert code == 0
    assert mock_notifier.sent == []  # dry-run: nothing actually "sent"
    assert "sent=False" in out

    # ---------------------------------------------------------------------- 7. dashboard: backend
    #    reads exactly the on-disk state the CLI steps above just produced, through the real API
    store = DashboardStore.open(data_dir)
    store.set_user(
        "admin", Role.ADMIN, hash_password(ADMIN_PASSWORD, params=FAST_SCRYPT), now=FIXED_NOW
    )

    loaded = load_config(environment=Environment.DEVELOPMENT, config_dir=config_dir)
    filtering = load_filtering_config(config_dir, now=FIXED_NOW)
    storage_config = load_storage_config(config_dir)
    clock = {"now": FIXED_NOW}
    provider = MockDnsProvider(now=lambda: clock["now"])
    paths = cli._resolved_paths(loaded)
    assert paths is not None

    # The collector, not the provider directly, populates /api/v1/devices — its first poll ever
    # only sets the watermark (no backfill by design), so a second poll is needed before any
    # client is actually observed and flushed to the store.
    collector = Collector(provider, store, tz=ZoneInfo("Europe/Rome"), now=lambda: clock["now"])
    collector.poll()
    clock["now"] = clock["now"] + timedelta(minutes=1)
    collector.poll()
    collector.flush()

    context = cli._dashboard_context(
        loaded, provider, store, filtering.config, storage_config, paths, lambda: FIXED_NOW
    )
    app = create_app(environment=Environment.DEVELOPMENT, provider=provider, dashboard=context)
    # https:// base_url: context.cookie_secure defaults True (DEV_PROFILE does not override it),
    # and a Secure cookie is never sent back to a plain-http TestClient origin.
    client = TestClient(app, base_url="https://testserver")

    try:
        login = client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}
        )
        assert login.status_code == 200, login.text

        overview = client.get("/api/v1/overview")
        assert overview.status_code == 200
        assert overview.json()["provider"]["status"] == "ok"
        # the live incident from step 5, surfaced through the real backend status() wiring
        assert overview.json()["open_incidents"] == 1

        alerts = client.get("/api/v1/alerts").json()
        assert [a["check_name"] for a in alerts] == ["storage"]
        assert alerts[0]["state"] == "incident"

        devices = client.get("/api/v1/devices")
        assert devices.status_code == 200 and len(devices.json()) == 16  # MockDnsProvider's fleet

        config_view = client.get("/api/v1/config").json()
        assert config_view["dns_provider"] == "mock"
        assert {s["id"] for s in config_view["blocklist_sources"]} == {"list-a", "list-b"}

        assert client.get("/api/v1/health").status_code == 200
    finally:
        store.close()

    # ------------------------------------------------------ 8. recovery clears the dashboard alert
    _run(config_dir, "monitoring", "status", "--apply", disk=_FakeDisk(10))
    store = DashboardStore.open(data_dir)
    try:
        context = cli._dashboard_context(
            loaded, provider, store, filtering.config, storage_config, paths, lambda: FIXED_NOW
        )
        recovered_app = create_app(
            environment=Environment.DEVELOPMENT, provider=provider, dashboard=context
        )
        recovered_client = TestClient(recovered_app, base_url="https://testserver")
        recovered_client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}
        )
        assert recovered_client.get("/api/v1/alerts").json() == []
    finally:
        store.close()
