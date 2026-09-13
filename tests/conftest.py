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


@pytest.fixture
def make_config_dir(tmp_path: Path) -> Callable[..., Path]:
    """Create <tmp>/config/app/<env>.yaml with the given text and return the config dir."""

    def factory(profile_text: str, env: str = "development", **extra_files: str) -> Path:
        config_dir = tmp_path / "config"
        (config_dir / "app").mkdir(parents=True, exist_ok=True)
        (config_dir / "app" / f"{env}.yaml").write_text(profile_text, encoding="utf-8")
        for relative, text in extra_files.items():
            target = config_dir / relative.replace("__", "/")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        return config_dir

    return factory
