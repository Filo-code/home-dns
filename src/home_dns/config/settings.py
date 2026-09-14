"""Application settings schema (A0 scope).

Only settings needed by A0 live here. Later phases add their own sections.
Environment-specific values are typed ``Deferred[...]`` so they may hold placeholders.
"""

from __future__ import annotations

from enum import StrEnum
from ipaddress import IPv4Address, IPv6Address
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from annotated_types import Ge, Le
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from home_dns.config.placeholders import Deferred

ENV_PREFIX = "HOME_DNS_"

PortNumber = Annotated[int, Ge(1), Le(65535)]


class Environment(StrEnum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class ProviderKind(StrEnum):
    MOCK = "mock"
    PIHOLE_V6 = "pihole_v6"


class NotifierKind(StrEnum):
    MOCK = "mock"
    FILE = "file"
    TELEGRAM = "telegram"


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PathsSettings(_Section):
    data_dir: Deferred[Path]
    log_dir: Deferred[Path]
    backup_dir: Deferred[Path]
    tmp_dir: Deferred[Path]


class MockProviderSettings(_Section):
    seed: int = 42


class PiHoleV6Settings(_Section):
    base_url: Deferred[AnyHttpUrl]
    request_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    verify_tls: bool = True


class DnsProviderSettings(_Section):
    kind: ProviderKind
    mock: MockProviderSettings = Field(default_factory=MockProviderSettings)
    pihole_v6: PiHoleV6Settings | None = None

    @model_validator(mode="after")
    def _selected_section_present(self) -> DnsProviderSettings:
        if self.kind is ProviderKind.PIHOLE_V6 and self.pihole_v6 is None:
            raise ValueError("dns_provider.pihole_v6 is required when kind is 'pihole_v6'")
        return self


class ApiSettings(_Section):
    bind_host: Deferred[IPv4Address | IPv6Address]
    port: Deferred[PortNumber]
    # False only for plain-HTTP development on loopback; TLS termination is decided in C4.
    cookie_secure: Deferred[bool] = True
    session_idle_minutes: int = Field(default=720, ge=5, le=10080)
    session_absolute_hours: int = Field(default=168, ge=1, le=720)

    @model_validator(mode="after")
    def _lan_only(self) -> ApiSettings:
        host = self.bind_host
        if isinstance(host, IPv4Address | IPv6Address) and not (
            host.is_private or host.is_loopback or host.is_link_local or host.is_unspecified
        ):
            raise ValueError(f"api.bind_host {host} is public; the dashboard is LAN-only")
        return self


class MetricsSettings(_Section):
    """Collector cadence and rollup retention (docs/specs/a7-backend.md §6). Hourly retention
    is storage.yaml's ``retention.query_history_days``, not repeated here."""

    collector_enabled: bool = True
    poll_interval_seconds: int = Field(default=60, ge=10, le=600)
    flush_interval_seconds: int = Field(default=300, ge=60, le=3600)
    timezone: str = "Europe/Rome"
    minute_retention_hours: int = Field(default=48, ge=1, le=168)
    day_retention_days: int = Field(default=365, ge=31, le=3650)

    @model_validator(mode="after")
    def _valid(self) -> MetricsSettings:
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(
                f"metrics.timezone {self.timezone!r} is not a known time zone"
            ) from exc
        if self.flush_interval_seconds < self.poll_interval_seconds:
            raise ValueError("metrics.flush_interval_seconds must be >= poll_interval_seconds")
        return self


class NotifierSettings(_Section):
    """Defaults to 'mock' (never sends anything real) so existing profiles need no changes."""

    kind: NotifierKind = NotifierKind.MOCK


class AppSettings(BaseSettings):
    """Settings from the profile file (passed as init kwargs) overridden by HOME_DNS_* env."""

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_nested_delimiter="__",
        extra="forbid",
        frozen=True,
    )

    paths: PathsSettings
    dns_provider: DnsProviderSettings
    api: ApiSettings
    notifier: NotifierSettings = Field(default_factory=NotifierSettings)
    metrics: MetricsSettings = Field(default_factory=MetricsSettings)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Environment variables win over the profile file. .env files are never read.
        return (env_settings, init_settings)


class SecretSettings(BaseSettings):
    """Secrets are read from environment variables only, never from files in the repo."""

    model_config = SettingsConfigDict(env_prefix=ENV_PREFIX, extra="ignore", frozen=True)

    pihole_app_password: SecretStr | None = None
    telegram_bot_token: SecretStr | None = Field(
        default=None, validation_alias="TELEGRAM_BOT_TOKEN"
    )
    telegram_chat_id: str | None = Field(default=None, validation_alias="TELEGRAM_CHAT_ID")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (env_settings,)
