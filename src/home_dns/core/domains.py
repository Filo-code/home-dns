"""Domain-name normalization and matching shared by rules, protected domains and pipelines."""

from __future__ import annotations

import re
from ipaddress import ip_address

MAX_DOMAIN_LENGTH = 253
_LABEL_RE = re.compile(r"(?!-)[a-z0-9_-]{1,63}(?<!-)")


class InvalidDomainError(ValueError):
    """A value is not an acceptable fully-qualified domain name."""


def normalize_domain(value: str) -> str:
    """Return the lower-case ASCII (punycode) form of a domain, or raise InvalidDomainError.

    Rejects wildcards (use include_subdomains instead), IP literals, single-label names
    (a TLD-only rule would affect everything below it) and syntactically invalid labels.
    """
    candidate = value.strip().rstrip(".").lower()
    if not candidate:
        raise InvalidDomainError("domain is empty")
    if "*" in candidate:
        raise InvalidDomainError(f"{value!r}: wildcards are not allowed; use include_subdomains")
    try:
        ip_address(candidate)
    except ValueError:
        pass
    else:
        raise InvalidDomainError(f"{value!r}: IP addresses are not domains")
    if candidate.isascii():
        ascii_name = candidate
    else:
        try:
            ascii_name = candidate.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise InvalidDomainError(f"{value!r}: invalid internationalized name") from exc
    labels = ascii_name.split(".")
    if len(labels) < 2:
        raise InvalidDomainError(f"{value!r}: single-label names are not allowed")
    if len(ascii_name) > MAX_DOMAIN_LENGTH:
        raise InvalidDomainError(f"{value!r}: longer than {MAX_DOMAIN_LENGTH} characters")
    for label in labels:
        if not _LABEL_RE.fullmatch(label):
            raise InvalidDomainError(f"{value!r}: invalid label {label!r}")
    if labels[-1].isdigit():
        raise InvalidDomainError(f"{value!r}: top-level label cannot be numeric")
    return ascii_name


def covers(scope: str, *, include_subdomains: bool, name: str) -> bool:
    """True if a rule for ``scope`` applies to ``name`` (both already normalized)."""
    return name == scope or (include_subdomains and name.endswith("." + scope))
