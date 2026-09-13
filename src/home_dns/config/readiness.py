"""Readiness: is a loaded configuration fit to run in the selected environment?

Every leaf setting is classified:

- ``ready``                a real value usable in production
- ``optional_unset``       an optional value left empty
- ``dev_only``             valid only for development/mock (error in production)
- ``missing_required``     <<REQUIRED:...>> in an active field, or a required secret absent
- ``missing_audit``        <<AUDIT:...>> in an active field (resolved in Stage B)
- ``inactive_placeholder`` a placeholder in a section this run does not use
- ``advisory``             allowed but discouraged (warning)
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from ipaddress import IPv4Address, IPv6Address
from pathlib import Path

from pydantic import BaseModel

from home_dns.config.placeholders import Placeholder, PlaceholderKind
from home_dns.config.settings import AppSettings, Environment, ProviderKind, SecretSettings


class Status(StrEnum):
    READY = "ready"
    OPTIONAL_UNSET = "optional_unset"
    DEV_ONLY = "dev_only"
    MISSING_REQUIRED = "missing_required"
    MISSING_AUDIT = "missing_audit"
    INACTIVE_PLACEHOLDER = "inactive_placeholder"
    ADVISORY = "advisory"


class Severity(StrEnum):
    OK = "ok"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class Finding:
    path: str
    status: Status
    severity: Severity
    message: str


@dataclass(frozen=True)
class ReadinessReport:
    environment: Environment
    findings: tuple[Finding, ...]

    @property
    def errors(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity is Severity.ERROR)

    @property
    def warnings(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity is Severity.WARNING)

    def is_ready(self, *, strict: bool = False) -> bool:
        return not self.errors and not (strict and self.warnings)


def _iter_leaves(model: BaseModel, prefix: str = "") -> Iterator[tuple[str, object]]:
    for name in type(model).model_fields:
        value = getattr(model, name)
        path = f"{prefix}.{name}" if prefix else name
        if isinstance(value, BaseModel) and not isinstance(value, Placeholder):
            yield from _iter_leaves(value, path)
        else:
            yield path, value


def _is_active(path: str, settings: AppSettings) -> bool:
    kind = settings.dns_provider.kind
    if path.startswith("dns_provider.mock"):
        return kind is ProviderKind.MOCK
    if path.startswith("dns_provider.pihole_v6"):
        return kind is ProviderKind.PIHOLE_V6
    return True


def _classify(path: str, value: object, settings: AppSettings, env: Environment) -> Finding:
    production = env is Environment.PRODUCTION

    if isinstance(value, Placeholder):
        if not _is_active(path, settings):
            return Finding(
                path,
                Status.INACTIVE_PLACEHOLDER,
                Severity.INFO,
                f"{value.token} (section not used by this configuration)",
            )
        if value.kind is PlaceholderKind.AUDIT:
            return Finding(
                path,
                Status.MISSING_AUDIT,
                Severity.ERROR,
                f"{value.token} must be resolved by the Stage B audits",
            )
        return Finding(
            path, Status.MISSING_REQUIRED, Severity.ERROR, f"{value.token} must be supplied"
        )

    if value is None:
        return Finding(path, Status.OPTIONAL_UNSET, Severity.OK, "not set")

    dev_severity = Severity.ERROR if production else Severity.INFO
    if path == "dns_provider.kind" and value is ProviderKind.MOCK:
        return Finding(
            path, Status.DEV_ONLY, dev_severity, "mock provider is for development and tests only"
        )
    if path.startswith("paths.") and isinstance(value, Path) and not value.is_absolute():
        return Finding(
            path,
            Status.DEV_ONLY,
            dev_severity,
            f"relative path {str(value)!r} is only allowed in development",
        )
    if (
        production
        and path == "api.bind_host"
        and isinstance(value, IPv4Address | IPv6Address)
        and value.is_unspecified
    ):
        return Finding(
            path,
            Status.ADVISORY,
            Severity.WARNING,
            "binds all interfaces; prefer the specific LAN address",
        )
    return Finding(path, Status.READY, Severity.OK, "set")


def evaluate_readiness(
    settings: AppSettings, secrets: SecretSettings, environment: Environment
) -> ReadinessReport:
    findings = [
        _classify(path, value, settings, environment)
        for path, value in _iter_leaves(settings)
        # Real values in unused sections are irrelevant; placeholders there are still reported.
        if _is_active(path, settings) or isinstance(value, Placeholder)
    ]
    if settings.dns_provider.kind is ProviderKind.PIHOLE_V6:
        if secrets.pihole_app_password is None:
            findings.append(
                Finding(
                    "secrets.pihole_app_password",
                    Status.MISSING_REQUIRED,
                    Severity.ERROR,
                    "HOME_DNS_PIHOLE_APP_PASSWORD is not set",
                )
            )
        else:
            findings.append(
                Finding("secrets.pihole_app_password", Status.READY, Severity.OK, "set")
            )
    return ReadinessReport(environment=environment, findings=tuple(findings))
