"""Test-wide safety rails: environment isolation and an offline network guard."""

from __future__ import annotations

import os
import socket
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


class NetworkAccessBlockedError(RuntimeError):
    """Raised when a test tries to reach a non-loopback address."""


@pytest.fixture(autouse=True)
def _isolate_home_dns_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("HOME_DNS_"):
            monkeypatch.delenv(key)


@pytest.fixture(autouse=True)
def _block_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.get_closest_marker("network"):
        return

    def guard(original: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(sock: socket.socket, address: Any) -> Any:
            if isinstance(address, tuple) and str(address[0]) not in _LOOPBACK:
                raise NetworkAccessBlockedError(f"network access blocked in tests: {address!r}")
            return original(sock, address)

        return wrapper

    monkeypatch.setattr(socket.socket, "connect", guard(socket.socket.connect))
    monkeypatch.setattr(socket.socket, "connect_ex", guard(socket.socket.connect_ex))


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def repo_config_dir() -> Path:
    return REPO_ROOT / "config"


DEV_PROFILE = """\
environment: development
paths:
  data_dir: .local/data
  log_dir: .local/logs
  backup_dir: .local/backups
  tmp_dir: .local/tmp
dns_provider:
  kind: mock
  mock:
    seed: 7
api:
  bind_host: 127.0.0.1
  port: 8080
"""

PROD_READY_PROFILE = """\
environment: production
paths:
  data_dir: /srv/home-dns/data
  log_dir: /srv/home-dns/logs
  backup_dir: /srv/home-dns/backups
  tmp_dir: /srv/home-dns/tmp
dns_provider:
  kind: pihole_v6
  pihole_v6:
    base_url: http://192.0.2.53
api:
  bind_host: 192.0.2.53
  port: 8080
"""


# Minimal valid filtering configuration (A1). Keys use "__" for "/" like extra_files.
FILTERING_FILES: dict[str, str] = {
    "groups__groups.yaml": """\
schema_version: 1
groups:
  - {id: DEFAULT, description: Default devices, policy: standard}
  - {id: SMART-TV, description: TVs, policy: conservative}
""",
    "policies__policies.yaml": """\
schema_version: 1
policies:
  - {id: standard, description: Standard, blocklists: [list-a, list-b]}
  - {id: conservative, description: Conservative, blocklists: [list-b]}
""",
    "blocklists__sources.yaml": """\
schema_version: 1
sources:
  - id: list-a
    name: List A
    homepage: https://lists.example/a
    license: GPL-3.0
    format: adblock
    categories: [advertising, tracking]
    urls:
      primary: https://cdn.example/a.txt
      fallback: https://mirror.example/a.txt
    update_interval_hours: 24
  - id: list-b
    name: List B
    homepage: https://lists.example/b
    license: GPL-3.0
    format: domains
    categories: [malware, phishing]
    urls: {primary: https://cdn.example/b.txt}
    update_interval_hours: 12
""",
    "rules__allow.yaml": "schema_version: 1\nrules: []\n",
    "rules__deny.yaml": "schema_version: 1\nrules: []\n",
    "rules__regex.yaml": "schema_version: 1\nrules: []\n",
    "protected-domains__technology.yaml": """\
schema_version: 1
category: technology
description: Technology platforms
domains:
  - {domain: googlevideo.example, include_subdomains: true, reason: video CDN, source: test}
""",
}

# Minimal valid storage configuration (A4). Same thresholds/shape as the repo's own file.
STORAGE_FILES: dict[str, str] = {
    "storage__storage.yaml": """\
schema_version: 1
disk_usage_thresholds_percent:
  healthy_below: 70
  warning_from: 70
  auto_cleanup_from: 80
  emergency_from: 90
retention:
  logs_max_bytes: 10485760
  logs_backup_count: 5
  temp_max_age_hours: 24
  backups_keep: 7
  query_history_days: 30
""",
}

# Minimal valid monitoring configuration (A5). Same shape as the repo's own file.
MONITORING_FILES: dict[str, str] = {
    "monitoring__monitoring.yaml": """\
schema_version: 1
incident:
  incident_after: 2
  recovered_after: 1
  cooldown_seconds: 0
restart_budget:
  max_attempts: 5
  base_delay_seconds: 1.0
  max_delay_seconds: 300.0
  backoff_factor: 2.0
""",
}

# Minimal valid anomaly-detection configuration (foundation phase). Same shape as the repo's
# own file — disabled by default, same as the shipped config.
ANOMALY_FILES: dict[str, str] = {
    "anomaly-detection__anomaly-detection.yaml": """\
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
overrides: {}
""",
}

# Minimal valid Telegram alerting configuration (A6). Same shape as the repo's own file.
TELEGRAM_FILES: dict[str, str] = {
    "telegram__alerts.yaml": """\
schema_version: 1
anti_spam:
  cooldown_seconds: 300
  rate_limit_per_hour: 20
  deduplicate: true
  incident_state_tracking: true
  send_recovery: true
severities:
  CRITICAL: [dns_down, storage_above_90, failed_update]
  WARNING: [storage_above_70, storage_above_80, blocklist_update_failure]
  INFO: [service_recovered, notify_test]
""",
}


@pytest.fixture
def make_config_dir(tmp_path: Path) -> Callable[..., Path]:
    """Create <tmp>/config with app/<env>.yaml, valid filtering/storage/monitoring/telegram sets
    and optional extras.

    Pass ``filtering=False`` / ``storage=False`` / ``monitoring=False`` / ``telegram=False`` /
    ``anomaly=False`` to
    omit those default file sets; extra files override defaults of any set.
    """

    def factory(
        profile_text: str,
        env: str = "development",
        *,
        filtering: bool = True,
        storage: bool = True,
        monitoring: bool = True,
        telegram: bool = True,
        anomaly: bool = True,
        **extra_files: str,
    ) -> Path:
        config_dir = tmp_path / "config"
        (config_dir / "app").mkdir(parents=True, exist_ok=True)
        (config_dir / "app" / f"{env}.yaml").write_text(profile_text, encoding="utf-8")
        files = {
            **(FILTERING_FILES if filtering else {}),
            **(STORAGE_FILES if storage else {}),
            **(MONITORING_FILES if monitoring else {}),
            **(TELEGRAM_FILES if telegram else {}),
            **(ANOMALY_FILES if anomaly else {}),
            **extra_files,
        }
        for relative, text in files.items():
            target = config_dir / relative.replace("__", "/")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        return config_dir

    return factory
