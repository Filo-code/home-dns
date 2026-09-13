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


@pytest.fixture
def make_config_dir(tmp_path: Path) -> Callable[..., Path]:
    """Create <tmp>/config with app/<env>.yaml, a valid filtering set and optional extra files.

    Pass ``filtering=False`` to omit the filtering files; extra files override defaults.
    """

    def factory(
        profile_text: str, env: str = "development", *, filtering: bool = True, **extra_files: str
    ) -> Path:
        config_dir = tmp_path / "config"
        (config_dir / "app").mkdir(parents=True, exist_ok=True)
        (config_dir / "app" / f"{env}.yaml").write_text(profile_text, encoding="utf-8")
        files = {**(FILTERING_FILES if filtering else {}), **extra_files}
        for relative, text in files.items():
            target = config_dir / relative.replace("__", "/")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        return config_dir

    return factory
