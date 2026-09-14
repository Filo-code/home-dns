"""Application settings schema (A0 scope).

Only settings needed by A0 live here. Later phases add their own sections.
Environment-specific values are typed ``Deferred[...]`` so they may hold placeholders.
"""

from __future__ import annotations

from enum import StrEnum
from ipaddress import IPv4Address, IPv6Address
from pathlib import Path
from typing import Annotated

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
