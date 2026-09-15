"""Load config/vpn/vpn.yaml — VPN *foundation* configuration only.

This module defines and validates the future WireGuard architecture's config shape. It does not
implement a VPN: nothing here writes a WireGuard config file, generates a key, opens a port, or
touches routing/firewall/NAT. See docs/vpn/architecture.md for the full design and
docs/vpn/fastweb-seven-prerequisites.md for what must be verified (B2) before any real
deployment. `enabled: false` is the shipped default and the only value a repository clone starts
with.

Same load pattern as config/monitoring.py: one owned YAML file, ``ConfigLoadError`` on any
problem.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from ipaddress import ip_address, ip_network
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from home_dns.config.loader import ConfigLoadError, check_file_hygiene, read_yaml_mapping

VPN_FILE = Path("vpn/vpn.yaml")


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class VpnClient(_Model):
    """One future WireGuard peer. ``public_key`` only — a private key must never appear in any
    committed file; see docs/vpn/architecture.md's key-handling section."""

    name: str = Field(min_length=1, max_length=64)
    public_key: str = Field(min_length=1)
    allowed_lan: bool = False

    @field_validator("public_key")
    @classmethod
    def _not_a_private_key_placeholder(cls, value: str) -> str:
        lowered = value.lower()
        if "private" in lowered or lowered.startswith("wgprivkey"):
            raise ValueError("public_key looks like it might be a private key; refusing to load")
        return value


class VpnConfig(_Model):
    enabled: bool = False
    interface_name: str = Field(min_length=1, max_length=15)  # Linux IFNAMSIZ limit
    subnet: str
    server_address: str
    dns_address: str
    allowed_networks: tuple[str, ...] = ()
    full_tunnel: bool = False
    clients: tuple[VpnClient, ...] = ()

    @field_validator("subnet")
    @classmethod
    def _valid_cidr(cls, value: str) -> str:
        try:
            network = ip_network(value, strict=True)
        except ValueError as exc:
            raise ValueError(f"{value!r} is not a valid CIDR network") from exc
        if not network.is_private:
            raise ValueError(f"{value!r} is not a private (RFC 1918) network")
        return value

    @model_validator(mode="after")
    def _addresses_inside_subnet(self) -> VpnConfig:
        network = ip_network(self.subnet, strict=True)
        try:
            server_addr = ip_address(self.server_address)
        except ValueError as exc:
            raise ValueError(
                f"server_address {self.server_address!r} is not a valid IP address"
            ) from exc
        if server_addr not in network:
            raise ValueError(f"server_address {self.server_address!r} is not inside {self.subnet}")
        # dns_address may legitimately be a LAN address (Pi-hole's existing LAN IP) rather than
        # the VPN subnet — it is not restricted to the VPN subnet the way server_address is.
        try:
            ip_address(self.dns_address)
        except ValueError as exc:
            raise ValueError(f"dns_address {self.dns_address!r} is not a valid IP address") from exc
        for cidr in self.allowed_networks:
            try:
                ip_network(cidr, strict=True)
            except ValueError as exc:
                raise ValueError(f"allowed_networks entry {cidr!r} is not a valid CIDR") from exc
        return self


class _File(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1]
    vpn: VpnConfig


@dataclass(frozen=True)
class LoadedVpnConfig:
    vpn: VpnConfig


def vpn_config_files(config_dir: Path) -> list[Path]:
    return [config_dir / VPN_FILE]


class VpnSubnetConflictError(ValueError):
    """The configured VPN subnet overlaps a real, known network. Real network identifiers must
    never be hard-coded in src/ or config/ (tests/architecture/test_no_real_network_values.py),
    so this check only ever runs against subnets the caller supplies explicitly — for example a
    human operator following docs/vpn/fastweb-seven-prerequisites.md, or a future B2-informed
    script. There is deliberately no built-in default."""


def check_no_subnet_conflicts(vpn: VpnConfig, known_subnets: Sequence[str]) -> None:
    """Raises VpnSubnetConflictError if ``vpn.subnet`` overlaps any of ``known_subnets``."""
    candidate = ip_network(vpn.subnet, strict=True)
    for other in known_subnets:
        network = ip_network(other, strict=True)
        if candidate.overlaps(network):
            raise VpnSubnetConflictError(
                f"VPN subnet {vpn.subnet!r} overlaps known network {other!r}"
            )


def load_vpn_config(config_dir: Path) -> LoadedVpnConfig:
    """Raises ConfigLoadError on a missing file, hygiene problems or schema errors. Loading this
    config does not enable anything — the caller must still check ``.vpn.enabled`` and, even
    then, no code in this repository currently acts on it (foundation phase only). Does not
    check for a real-network subnet conflict — see ``check_no_subnet_conflicts``."""
    path = config_dir / VPN_FILE
    data = read_yaml_mapping(path)
    check_file_hygiene(data, path)
    try:
        parsed = _File.model_validate(data)
    except ValidationError as exc:
        parts = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or '<root>'}: {e['msg']}"
            for e in exc.errors(include_input=False, include_url=False)
        )
        raise ConfigLoadError(f"{path}: {parts}") from exc
    return LoadedVpnConfig(vpn=parsed.vpn)
