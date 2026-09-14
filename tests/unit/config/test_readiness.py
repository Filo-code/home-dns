from collections.abc import Callable
from pathlib import Path

import pytest

from home_dns.config.loader import load_config
from home_dns.config.readiness import Severity, Status, evaluate_readiness
from home_dns.config.settings import Environment
from tests.conftest import DEV_PROFILE, PROD_READY_PROFILE

MakeConfigDir = Callable[..., Path]


def _report(config_dir: Path, env: Environment, profile: Path | None = None):  # type: ignore[no-untyped-def]
    loaded = load_config(environment=env, config_dir=config_dir, profile=profile)
    return evaluate_readiness(loaded.settings, loaded.secrets, env)


def _status(report, path: str) -> tuple[Status, Severity]:  # type: ignore[no-untyped-def]
    finding = next(f for f in report.findings if f.path == path)
    return finding.status, finding.severity


def test_committed_development_profile_is_ready(repo_config_dir: Path) -> None:
    report = _report(repo_config_dir, Environment.DEVELOPMENT)
    assert report.is_ready(strict=True)
    assert _status(report, "dns_provider.kind") == (Status.DEV_ONLY, Severity.INFO)
    assert _status(report, "paths.data_dir") == (Status.DEV_ONLY, Severity.INFO)
    assert _status(report, "api.port") == (Status.READY, Severity.OK)
    assert not any(f.path.startswith("dns_provider.pihole_v6") for f in report.findings)


def test_committed_production_example_is_not_ready(repo_config_dir: Path) -> None:
    report = _report(
        repo_config_dir, Environment.PRODUCTION, repo_config_dir / "app" / "production.example.yaml"
    )
    assert not report.is_ready()
    errors = {f.path: f.status for f in report.errors}
    assert errors == {
        "paths.data_dir": Status.MISSING_AUDIT,
        "paths.log_dir": Status.MISSING_AUDIT,
        "paths.backup_dir": Status.MISSING_AUDIT,
        "paths.tmp_dir": Status.MISSING_AUDIT,
        "dns_provider.pihole_v6.base_url": Status.MISSING_AUDIT,
        "api.bind_host": Status.MISSING_AUDIT,
        "api.port": Status.MISSING_REQUIRED,
        "api.cookie_secure": Status.MISSING_REQUIRED,
        "secrets.pihole_app_password": Status.MISSING_REQUIRED,
    }


def test_fully_resolved_production_profile_is_ready(
    make_config_dir: MakeConfigDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME_DNS_PIHOLE_APP_PASSWORD", "x")
    report = _report(make_config_dir(PROD_READY_PROFILE, env="production"), Environment.PRODUCTION)
    assert report.is_ready(strict=True)
    assert all(f.severity is Severity.OK for f in report.findings)
    assert _status(report, "secrets.pihole_app_password") == (Status.READY, Severity.OK)


def test_production_rejects_dev_only_values(
    make_config_dir: MakeConfigDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    text = DEV_PROFILE.replace("environment: development", "environment: production").replace(
        ".local/logs", "/srv/logs"
    )
    report = _report(make_config_dir(text, env="production"), Environment.PRODUCTION)
    errors = {f.path: f.status for f in report.errors}
    assert errors == {
        "paths.data_dir": Status.DEV_ONLY,
        "paths.backup_dir": Status.DEV_ONLY,
        "paths.tmp_dir": Status.DEV_ONLY,
        "dns_provider.kind": Status.DEV_ONLY,
    }


def test_active_placeholder_blocks_development_too(make_config_dir: MakeConfigDir) -> None:
    text = DEV_PROFILE.replace("port: 8080", 'port: "<<REQUIRED:api.port>>"')
    report = _report(make_config_dir(text), Environment.DEVELOPMENT)
    assert not report.is_ready()
    assert _status(report, "api.port") == (Status.MISSING_REQUIRED, Severity.ERROR)


def test_placeholders_in_inactive_section_are_informational(make_config_dir: MakeConfigDir) -> None:
    text = DEV_PROFILE.replace(
        "  mock:\n",
        '  pihole_v6:\n    base_url: "<<AUDIT:dns_provider.pihole_v6.base_url>>"\n  mock:\n',
    )
    report = _report(make_config_dir(text), Environment.DEVELOPMENT)
    assert report.is_ready()
    assert _status(report, "dns_provider.pihole_v6.base_url") == (
        Status.INACTIVE_PLACEHOLDER,
        Severity.INFO,
    )
    assert not any(f.path == "dns_provider.pihole_v6.verify_tls" for f in report.findings)


def test_unspecified_bind_address_warns_in_production(
    make_config_dir: MakeConfigDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME_DNS_PIHOLE_APP_PASSWORD", "x")
    text = PROD_READY_PROFILE.replace("bind_host: 192.0.2.53", "bind_host: 0.0.0.0")
    report = _report(make_config_dir(text, env="production"), Environment.PRODUCTION)
    assert _status(report, "api.bind_host") == (Status.ADVISORY, Severity.WARNING)
    assert report.is_ready()
    assert not report.is_ready(strict=True)


def test_missing_pihole_password_blocks_any_environment(make_config_dir: MakeConfigDir) -> None:
    text = DEV_PROFILE.replace(
        "  kind: mock\n", "  kind: pihole_v6\n  pihole_v6:\n    base_url: http://192.0.2.53\n"
    )
    report = _report(make_config_dir(text), Environment.DEVELOPMENT)
    assert _status(report, "secrets.pihole_app_password") == (
        Status.MISSING_REQUIRED,
        Severity.ERROR,
    )
