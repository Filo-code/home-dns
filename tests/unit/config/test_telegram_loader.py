from collections.abc import Callable
from pathlib import Path

import pytest

from home_dns.config.loader import ConfigLoadError
from home_dns.config.telegram import load_telegram_config, telegram_config_files
from tests.conftest import DEV_PROFILE

MakeConfigDir = Callable[..., Path]


def test_repository_telegram_config_is_valid(repo_config_dir: Path) -> None:
    config = load_telegram_config(repo_config_dir)
    assert config.anti_spam.cooldown_seconds == 300
    assert config.anti_spam.rate_limit_per_hour == 20
    assert config.event_severity["storage_above_90"] == "critical"
    assert config.event_severity["storage_above_70"] == "warning"
    assert config.event_severity["service_recovered"] == "info"
    assert config.send_recovery is True


def test_fixture_telegram_config_is_valid(make_config_dir: MakeConfigDir) -> None:
    config = load_telegram_config(make_config_dir(DEV_PROFILE))
    assert config.event_severity["dns_down"] == "critical"


def test_missing_telegram_file_is_a_load_error(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE, telegram=False)
    with pytest.raises(ConfigLoadError, match="file not found"):
        load_telegram_config(config_dir)


def test_null_anti_spam_values_mean_no_limit(make_config_dir: MakeConfigDir) -> None:
    content = """\
schema_version: 1
anti_spam:
  cooldown_seconds: null
  rate_limit_per_hour: null
  deduplicate: true
  incident_state_tracking: true
  send_recovery: true
severities:
  CRITICAL: [dns_down]
  WARNING: []
  INFO: []
"""
    config_dir = make_config_dir(DEV_PROFILE, **{"telegram__alerts.yaml": content})
    config = load_telegram_config(config_dir)
    assert config.anti_spam.cooldown_seconds is None
    assert config.anti_spam.rate_limit_per_hour is None


def test_event_listed_under_two_severities_is_rejected(make_config_dir: MakeConfigDir) -> None:
    content = """\
schema_version: 1
anti_spam:
  cooldown_seconds: 300
  rate_limit_per_hour: 20
  deduplicate: true
  incident_state_tracking: true
  send_recovery: true
severities:
  CRITICAL: [dns_down]
  WARNING: [dns_down]
  INFO: []
"""
    config_dir = make_config_dir(DEV_PROFILE, **{"telegram__alerts.yaml": content})
    with pytest.raises(ConfigLoadError, match="more than one severity"):
        load_telegram_config(config_dir)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("schema_version: 2\n", "schema_version"),
        ("schema_version: 1\n", "anti_spam"),
        (
            "schema_version: 1\nanti_spam: {cooldown_seconds: 300, rate_limit_per_hour: 20, "
            "deduplicate: true, incident_state_tracking: true, send_recovery: true}\n"
            "severities: {CRITICAL: [], WARNING: [], INFO: []}\nextra: true\n",
            "extra",
        ),
        (
            "schema_version: 1\nanti_spam: {cooldown_seconds: 300, rate_limit_per_hour: 20, "
            "deduplicate: true, incident_state_tracking: true, send_recovery: true, token: abc}\n"
            "severities: {CRITICAL: [], WARNING: [], INFO: []}\n",
            "secret-like keys",
        ),
    ],
)
def test_invalid_telegram_configs_are_rejected(
    make_config_dir: MakeConfigDir, content: str, message: str
) -> None:
    config_dir = make_config_dir(DEV_PROFILE, **{"telegram__alerts.yaml": content})
    with pytest.raises(ConfigLoadError, match=message):
        load_telegram_config(config_dir)


def test_telegram_config_files_returns_the_one_owned_path(repo_config_dir: Path) -> None:
    files = telegram_config_files(repo_config_dir)
    assert files == [repo_config_dir / "telegram" / "alerts.yaml"]
