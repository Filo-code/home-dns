"""Composition root: configuration -> readiness -> concrete dependencies."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from home_dns.config.loader import LoadedConfig
from home_dns.config.readiness import ReadinessReport, evaluate_readiness
from home_dns.config.settings import ProviderKind
from home_dns.providers.base import DnsProvider, ProviderNotAvailableError
from home_dns.providers.mock import MockDnsProvider
from home_dns.providers.pihole_v6 import PiholeV6Provider


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
    config: LoadedConfig,
    *,
    now: Callable[[], datetime] | None = None,
    source_urls: Mapping[str, str] | None = None,
) -> DnsProvider:
    provider_settings = config.settings.dns_provider
    if provider_settings.kind is ProviderKind.MOCK:
        return MockDnsProvider(
            seed=provider_settings.mock.seed, now=now or (lambda: datetime.now(UTC))
        )
    if provider_settings.kind is ProviderKind.PIHOLE_V6:
        pihole_settings = provider_settings.pihole_v6
        if pihole_settings is None:  # pragma: no cover - enforced by DnsProviderSettings
            raise ProviderNotAvailableError("dns_provider.pihole_v6 is not configured")
        password = config.secrets.pihole_app_password
        if password is None:
            raise ProviderNotAvailableError(
                "dns_provider.kind is 'pihole_v6' but HOME_DNS_PIHOLE_APP_PASSWORD is not set"
            )
        return PiholeV6Provider(
            base_url=str(pihole_settings.base_url),
            password=password.get_secret_value(),
            request_timeout_seconds=pihole_settings.request_timeout_seconds,
            verify_tls=pihole_settings.verify_tls,
            source_urls=source_urls,
            now=now or (lambda: datetime.now(UTC)),
        )
    raise ProviderNotAvailableError(  # pragma: no cover - only two ProviderKind members exist
        f"provider {provider_settings.kind.value!r} is not implemented yet"
    )


def build_runtime(
    config: LoadedConfig,
    *,
    now: Callable[[], datetime] | None = None,
    source_urls: Mapping[str, str] | None = None,
) -> Runtime:
    report = evaluate_readiness(config.settings, config.secrets, config.environment)
    if not report.is_ready():
        raise StartupRefusedError(report)
    provider = build_provider(config, now=now, source_urls=source_urls)
    return Runtime(config=config, report=report, provider=provider)
