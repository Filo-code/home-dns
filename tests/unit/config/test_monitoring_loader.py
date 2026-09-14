from collections.abc import Callable
from pathlib import Path

import pytest

from home_dns.config.loader import ConfigLoadError
from home_dns.config.monitoring import load_monitoring_config, monitoring_config_files
from tests.conftest import DEV_PROFILE

MakeConfigDir = Callable[..., Path]


def test_repository_monitoring_config_is_valid(repo_config_dir: Path) -> None:
    config = load_monitoring_config(repo_config_dir)
    assert config.incident.incident_after >= 1
    assert config.restart_budget.max_attempts >= 1


def test_fixture_monitoring_config_is_valid(make_config_dir: MakeConfigDir) -> None:
    config = load_monitoring_config(make_config_dir(DEV_PROFILE))
    assert config.incident.incident_after == 2
    assert config.restart_budget.max_attempts == 5


def test_missing_monitoring_file_is_a_load_error(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE, monitoring=False)
    with pytest.raises(ConfigLoadError, match="file not found"):
        load_monitoring_config(config_dir)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("schema_version: 2\n", "schema_version"),
        ("schema_version: 1\n", "incident"),
        (
            "schema_version: 1\nincident: {incident_after: 0, recovered_after: 1, "
            "cooldown_seconds: 0}\nrestart_budget: {max_attempts: 5, base_delay_seconds: 1.0, "
            "max_delay_seconds: 300.0, backoff_factor: 2.0}\n",
            "incident_after",
        ),
        (
            "schema_version: 1\nincident: {incident_after: 2, recovered_after: 1, "
            "cooldown_seconds: 0}\nrestart_budget: {max_attempts: 5, base_delay_seconds: 10, "
            "max_delay_seconds: 5, backoff_factor: 2.0}\n",
            "max_delay_seconds",
        ),
        (
            "schema_version: 1\nincident: {incident_after: 2, recovered_after: 1, "
            "cooldown_seconds: 0}\nrestart_budget: {max_attempts: 5, base_delay_seconds: 1.0, "
            "max_delay_seconds: 300.0, backoff_factor: 2.0}\nextra: true\n",
            "extra",
        ),
        (
            "schema_version: 1\nincident: {incident_after: 2, recovered_after: 1, "
            "cooldown_seconds: 0}\nrestart_budget: {max_attempts: 5, base_delay_seconds: 1.0, "
            "max_delay_seconds: 300.0, backoff_factor: 2.0, token: abc}\n",
            "secret-like keys",
        ),
        (
            "schema_version: 1\nincident: '<<TODO>>'\n"
            "restart_budget: {max_attempts: 5, base_delay_seconds: 1.0, "
            "max_delay_seconds: 300.0, backoff_factor: 2.0}\n",
            "malformed placeholder",
        ),
    ],
)
def test_invalid_monitoring_configs_are_rejected(
    make_config_dir: MakeConfigDir, content: str, message: str
) -> None:
    config_dir = make_config_dir(DEV_PROFILE, **{"monitoring__monitoring.yaml": content})
    with pytest.raises(ConfigLoadError, match=message):
        load_monitoring_config(config_dir)


def test_monitoring_config_files_returns_the_one_owned_path(repo_config_dir: Path) -> None:
    files = monitoring_config_files(repo_config_dir)
    assert files == [repo_config_dir / "monitoring" / "monitoring.yaml"]
