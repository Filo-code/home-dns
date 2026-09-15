from collections.abc import Callable
from pathlib import Path

import pytest

from home_dns.config.loader import ConfigLoadError
from home_dns.config.vpn import (
    VpnConfig,
    VpnSubnetConflictError,
    check_no_subnet_conflicts,
    load_vpn_config,
    vpn_config_files,
)
from tests.conftest import DEV_PROFILE

MakeConfigDir = Callable[..., Path]

# RFC 5737 documentation address space (TEST-NET-1) — same convention the rest of this
# codebase's fixtures already use, never a real address.
VALID_VPN_FILE = """\
schema_version: 1
vpn:
  enabled: false
  interface_name: wg0
  subnet: "192.0.2.0/24"
  server_address: "192.0.2.1"
  dns_address: "192.0.2.1"
  allowed_networks: []
  full_tunnel: false
  clients: []
"""


def test_repository_vpn_config_is_valid_and_disabled_by_default(repo_config_dir: Path) -> None:
    loaded = load_vpn_config(repo_config_dir)
    assert loaded.vpn.enabled is False
    assert loaded.vpn.clients == ()


def test_fixture_vpn_config_is_valid(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE, **{"vpn__vpn.yaml": VALID_VPN_FILE})
    loaded = load_vpn_config(config_dir)
    assert loaded.vpn.enabled is False
    assert loaded.vpn.interface_name == "wg0"
    assert loaded.vpn.subnet == "192.0.2.0/24"


def test_missing_vpn_file_is_a_load_error(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    with pytest.raises(ConfigLoadError, match="file not found"):
        load_vpn_config(config_dir)


def test_production_config_remains_valid_with_vpn_disabled(
    make_config_dir: MakeConfigDir,
) -> None:
    """Loading the VPN config while disabled must never fail or require any real deployment
    detail — disabled is the safe, always-valid state (design goal: "production startup must
    remain safe when VPN is disabled")."""
    config_dir = make_config_dir(DEV_PROFILE, **{"vpn__vpn.yaml": VALID_VPN_FILE})
    loaded = load_vpn_config(config_dir)
    assert loaded.vpn.enabled is False


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (VALID_VPN_FILE.replace("schema_version: 1", "schema_version: 2"), "schema_version"),
        ("schema_version: 1\nvpn: {}\n", "interface_name"),
        (VALID_VPN_FILE + "extra: true\n", "extra"),
        (VALID_VPN_FILE.replace('subnet: "192.0.2.0/24"', 'subnet: "not-a-cidr"'), "valid CIDR"),
        (
            VALID_VPN_FILE.replace('subnet: "192.0.2.0/24"', 'subnet: "8.8.8.0/24"'),
            "private",
        ),
        (
            VALID_VPN_FILE.replace('server_address: "192.0.2.1"', 'server_address: "192.0.3.1"'),
            "is not inside",
        ),
        (
            VALID_VPN_FILE.replace(
                "clients: []",
                'clients:\n  - name: laptop\n    public_key: "my-wireguard-private-key-abc"\n',
            ),
            "private key",
        ),
    ],
)
def test_invalid_vpn_configs_are_rejected(
    make_config_dir: MakeConfigDir, content: str, message: str
) -> None:
    config_dir = make_config_dir(DEV_PROFILE, **{"vpn__vpn.yaml": content})
    with pytest.raises(ConfigLoadError, match=message):
        load_vpn_config(config_dir)


def test_valid_client_with_public_key_only_is_accepted(make_config_dir: MakeConfigDir) -> None:
    content = VALID_VPN_FILE.replace(
        "clients: []",
        'clients:\n  - name: laptop\n    public_key: "AbCdEf1234567890PlaceholderPublicKey="\n'
        "    allowed_lan: false\n",
    )
    config_dir = make_config_dir(DEV_PROFILE, **{"vpn__vpn.yaml": content})
    loaded = load_vpn_config(config_dir)
    assert len(loaded.vpn.clients) == 1
    assert loaded.vpn.clients[0].name == "laptop"
    assert loaded.vpn.clients[0].allowed_lan is False


def test_vpn_config_files_returns_the_one_owned_path(repo_config_dir: Path) -> None:
    files = vpn_config_files(repo_config_dir)
    assert files == [repo_config_dir / "vpn" / "vpn.yaml"]


# ------------------------------------------------------------------ real-subnet conflict check
#
# This deliberately never runs against a hard-coded real address (see check_no_subnet_conflicts's
# own docstring and tests/architecture/test_no_real_network_values.py) — the caller supplies the
# subnet to check against, here a synthetic "known network" in documentation address space.


def _vpn(subnet: str, server_address: str = "192.0.2.1") -> VpnConfig:
    return VpnConfig(
        interface_name="wg0",
        subnet=subnet,
        server_address=server_address,
        dns_address=server_address,
    )


def test_conflicting_subnet_is_rejected() -> None:
    vpn = _vpn("198.51.100.0/24", server_address="198.51.100.1")
    with pytest.raises(VpnSubnetConflictError, match="overlaps known network"):
        check_no_subnet_conflicts(vpn, known_subnets=["198.51.100.0/24"])


def test_non_conflicting_subnet_is_accepted() -> None:
    vpn = _vpn("192.0.2.0/24")
    check_no_subnet_conflicts(vpn, known_subnets=["198.51.100.0/24", "203.0.113.0/24"])  # no raise


def test_no_known_subnets_means_no_conflict_possible() -> None:
    vpn = _vpn("192.0.2.0/24")
    check_no_subnet_conflicts(vpn, known_subnets=())  # no raise
