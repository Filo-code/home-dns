from collections.abc import Callable
from pathlib import Path

import pytest

from home_dns.bootstrap import StartupRefusedError, build_provider, build_runtime
from home_dns.config.loader import load_config
from home_dns.config.settings import Environment
from home_dns.providers.base import ProviderNotAvailableError
from home_dns.providers.mock import MockDnsProvider
from tests.conftest import DEV_PROFILE, PROD_READY_PROFILE

MakeConfigDir = Callable[..., Path]


def test_development_runtime_uses_mock_provider(make_config_dir: MakeConfigDir) -> None:
    loaded = load_config(
        environment=Environment.DEVELOPMENT, config_dir=make_config_dir(DEV_PROFILE)
    )
    runtime = build_runtime(loaded)
    assert isinstance(runtime.provider, MockDnsProvider)
    assert runtime.report.is_ready()


def test_mock_provider_receives_configured_seed(make_config_dir: MakeConfigDir) -> None:
    loaded = load_config(
        environment=Environment.DEVELOPMENT, config_dir=make_config_dir(DEV_PROFILE)
    )
    assert build_provider(loaded).list_clients()[0].total_queries == (
        MockDnsProvider(seed=7).list_clients()[0].total_queries
    )


def test_production_example_is_refused(repo_config_dir: Path) -> None:
    loaded = load_config(
        environment=Environment.PRODUCTION,
        config_dir=repo_config_dir,
        profile=repo_config_dir / "app" / "production.example.yaml",
    )
    with pytest.raises(StartupRefusedError) as excinfo:
        build_runtime(loaded)
    assert "api.port" in str(excinfo.value)
    assert len(excinfo.value.report.errors) == 9


def test_production_with_mock_provider_is_refused(make_config_dir: MakeConfigDir) -> None:
    text = PROD_READY_PROFILE.replace(
        "  kind: pihole_v6\n  pihole_v6:\n    base_url: http://192.0.2.53\n", "  kind: mock\n"
    )
    loaded = load_config(
        environment=Environment.PRODUCTION, config_dir=make_config_dir(text, env="production")
    )
    with pytest.raises(StartupRefusedError, match=r"dns_provider\.kind"):
        build_runtime(loaded)


def test_ready_pihole_configuration_reports_provider_not_available_until_c2(
    make_config_dir: MakeConfigDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME_DNS_PIHOLE_APP_PASSWORD", "x")
    loaded = load_config(
        environment=Environment.PRODUCTION,
        config_dir=make_config_dir(PROD_READY_PROFILE, env="production"),
    )
    with pytest.raises(ProviderNotAvailableError, match="C2"):
        build_runtime(loaded)
