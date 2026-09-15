from collections.abc import Callable
from pathlib import Path

import pytest

from home_dns.config.anomaly import anomaly_config_files, load_anomaly_config
from home_dns.config.loader import ConfigLoadError
from tests.conftest import DEV_PROFILE

MakeConfigDir = Callable[..., Path]

VALID_ANOMALY_FILE = """\
schema_version: 1
enabled: false
window_minutes: 30
max_entries_per_device: 2000
retention_days: 30
default:
  nxdomain_burst_count: 20
  nxdomain_burst_window_minutes: 5
  query_rate_spike_multiplier: 4.0
  query_rate_baseline_minutes: 10
  beaconing_min_repeats: 6
  beaconing_interval_tolerance_seconds: 5
  entropy_threshold: 3.5
  entropy_min_label_length: 12
  failure_burst_count: 15
  failure_burst_window_minutes: 5
overrides:
  PC:
    nxdomain_burst_count: 40
    nxdomain_burst_window_minutes: 5
    query_rate_spike_multiplier: 6.0
    query_rate_baseline_minutes: 10
    beaconing_min_repeats: 10
    beaconing_interval_tolerance_seconds: 3
    entropy_threshold: 4.0
    entropy_min_label_length: 14
    failure_burst_count: 30
    failure_burst_window_minutes: 5
"""


def test_repository_anomaly_config_is_valid_and_disabled_by_default(repo_config_dir: Path) -> None:
    config = load_anomaly_config(repo_config_dir)
    assert config.enabled is False
    assert config.retention_days >= 1
    assert config.analyzer.thresholds_for("DEFAULT") is not None
    assert config.analyzer.thresholds_for("PC") is not None
    assert config.analyzer.thresholds_for("SMART-TV") is not None
    assert config.analyzer.thresholds_for("XBOX") is not None


def test_fixture_anomaly_config_is_valid(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(
        DEV_PROFILE, **{"anomaly-detection__anomaly-detection.yaml": VALID_ANOMALY_FILE}
    )
    config = load_anomaly_config(config_dir)
    assert config.enabled is False
    assert config.retention_days == 30
    pc = config.analyzer.thresholds_for("PC")
    default = config.analyzer.thresholds_for("DEFAULT")
    assert pc.nxdomain_burst_count > default.nxdomain_burst_count  # PC is more permissive


def test_missing_anomaly_file_is_a_load_error(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE, anomaly=False)
    with pytest.raises(ConfigLoadError, match="file not found"):
        load_anomaly_config(config_dir)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (VALID_ANOMALY_FILE.replace("schema_version: 1", "schema_version: 2"), "schema_version"),
        ("schema_version: 1\nenabled: false\n", "window_minutes"),
        (VALID_ANOMALY_FILE + "extra_field: true\n", "extra_field"),
        (VALID_ANOMALY_FILE + "token: abc\n", "secret-like keys"),
        (
            VALID_ANOMALY_FILE.replace("nxdomain_burst_count: 20", "nxdomain_burst_count: 0"),
            "nxdomain_burst_count",
        ),
        (
            VALID_ANOMALY_FILE.replace(
                "  PC:",
                "  DEFAULT:\n"
                "    nxdomain_burst_count: 1\n"
                "    nxdomain_burst_window_minutes: 1\n"
                "    query_rate_spike_multiplier: 2.0\n"
                "    query_rate_baseline_minutes: 1\n"
                "    beaconing_min_repeats: 3\n"
                "    beaconing_interval_tolerance_seconds: 1\n"
                "    entropy_threshold: 1.0\n"
                "    entropy_min_label_length: 1\n"
                "    failure_burst_count: 1\n"
                "    failure_burst_window_minutes: 1\n"
                "  PC:",
            ),
            "duplicates 'default'",
        ),
    ],
)
def test_invalid_anomaly_configs_are_rejected(
    make_config_dir: MakeConfigDir, content: str, message: str
) -> None:
    config_dir = make_config_dir(
        DEV_PROFILE, **{"anomaly-detection__anomaly-detection.yaml": content}
    )
    with pytest.raises(ConfigLoadError, match=message):
        load_anomaly_config(config_dir)


def test_anomaly_config_files_returns_the_one_owned_path(repo_config_dir: Path) -> None:
    files = anomaly_config_files(repo_config_dir)
    assert files == [repo_config_dir / "anomaly-detection" / "anomaly-detection.yaml"]
