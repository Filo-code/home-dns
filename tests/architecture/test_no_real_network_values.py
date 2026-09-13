"""No real network identifiers may be hard-coded in code, config or frontend sources.

Allowed: loopback, unspecified, documentation ranges (192.0.2.0/24, 198.51.100.0/24,
203.0.113.0/24, 2001:db8::/32) and documentation MACs (00:00:5e:00:53:xx).
Audit documents under docs/ are intentionally out of scope.
"""

import re
from ipaddress import IPv4Address, IPv6Address, IPv6Network, ip_address
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCANNED = [REPO / "src", REPO / "config", REPO / "dashboard" / "frontend" / "src"]
SUFFIXES = {".py", ".yaml", ".yml", ".ts", ".tsx", ".json", ".toml", ".env", ".example"}

_IPV4_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
_IPV6_RE = re.compile(
    r"(?<![0-9a-fA-F:])(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{0,4}(?![0-9a-fA-F:])"
)
_MAC_RE = re.compile(r"(?<![0-9a-fA-F:])(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}(?![0-9a-fA-F:])")

_DOC_V4 = ("192.0.2.", "198.51.100.", "203.0.113.")


def _files() -> list[Path]:
    return [
        path
        for root in SCANNED
        if root.exists()
        for path in root.rglob("*")
        if path.is_file() and (path.suffix in SUFFIXES or path.name.endswith(".example.yaml"))
    ]


def _allowed_ip(text: str) -> bool:
    try:
        address = ip_address(text)
    except ValueError:
        return True  # not an address (e.g. a version string)
    if address.is_loopback or address.is_unspecified:
        return True
    if isinstance(address, IPv4Address):
        return text.startswith(_DOC_V4)
    assert isinstance(address, IPv6Address)
    return address in IPv6Network("2001:db8::/32")


def test_scanner_finds_files() -> None:
    assert any(path.suffix == ".py" for path in _files())


def test_no_real_ip_addresses() -> None:
    offenders = [
        f"{path.relative_to(REPO)}: {match}"
        for path in _files()
        for match in _IPV4_RE.findall(path.read_text(encoding="utf-8", errors="ignore"))
        + _IPV6_RE.findall(path.read_text(encoding="utf-8", errors="ignore"))
        if not _allowed_ip(match)
    ]
    assert not offenders, "\n".join(offenders)


def test_no_real_mac_addresses() -> None:
    offenders = [
        f"{path.relative_to(REPO)}: {match}"
        for path in _files()
        for match in _MAC_RE.findall(path.read_text(encoding="utf-8", errors="ignore"))
        if not match.lower().replace("-", ":").startswith("00:00:5e:00:53:")
    ]
    assert not offenders, "\n".join(offenders)


def test_detector_catches_real_values() -> None:
    assert not _allowed_ip("192.168.1.1")
    assert not _allowed_ip("10.0.0.5")
    assert not _allowed_ip("fd12:3456:789a::1")
    assert _allowed_ip("192.0.2.53") and _allowed_ip("2001:db8::10") and _allowed_ip("127.0.0.1")
