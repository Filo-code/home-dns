"""Composition root: configuration -> readiness -> concrete dependencies."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from home_dns.config.loader import LoadedConfig
from home_dns.config.readiness import ReadinessReport, evaluate_readiness
from home_dns.config.settings import ProviderKind
from home_dns.providers.base import DnsProvider, ProviderNotAvailableError
from home_dns.providers.mock import MockDnsProvider


class StartupRefusedError(Exception):
    """The configuration is not ready for the selected environment."""

    def __init__(self, report: ReadinessReport) -> None:
        self.report = report
        paths = ", ".join(f.path for f in report.errors)
        super().__init__(f"refusing to start in {report.environment.value}: {paths}")


@dataclass(frozen=True)
class Runtime:
    config: LoadedConfig
    report: ReadinessReport
    provider: DnsProvider


def build_provider(
    config: LoadedConfig, *, now: Callable[[], datetime] | None = None
) -> DnsProvider:
    provider_settings = config.settings.dns_provider
    if provider_settings.kind is ProviderKind.MOCK:
        return MockDnsProvider(
            seed=provider_settings.mock.seed, now=now or (lambda: datetime.now(UTC))
        )
    raise ProviderNotAvailableError(
        f"provider {provider_settings.kind.value!r} is not implemented yet (phase C2)"
    )


def build_runtime(config: LoadedConfig, *, now: Callable[[], datetime] | None = None) -> Runtime:
    report = evaluate_readiness(config.settings, config.secrets, config.environment)
    if not report.is_ready():
        raise StartupRefusedError(report)
    return Runtime(config=config, report=report, provider=build_provider(config, now=now))
