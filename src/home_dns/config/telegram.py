"""Load config/telegram/alerts.yaml (A6): the severity catalog and anti-spam policy."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from home_dns.config.loader import ConfigLoadError, check_file_hygiene, read_yaml_mapping
from home_dns.core.notify import AntiSpamPolicy, Severity

ALERTS_FILE = Path("telegram/alerts.yaml")

_SEVERITY_KEYS: dict[str, Severity] = {"CRITICAL": "critical", "WARNING": "warning", "INFO": "info"}


class _AntiSpamFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    cooldown_seconds: float | None = None
    rate_limit_per_hour: int | None = None
    deduplicate: bool
    incident_state_tracking: bool
    send_recovery: bool


class _File(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1]
    anti_spam: _AntiSpamFile
    severities: dict[Literal["CRITICAL", "WARNING", "INFO"], list[str]]


@dataclass(frozen=True)
class TelegramAlertsConfig:
    anti_spam: AntiSpamPolicy
    event_severity: dict[str, Severity]
    send_recovery: bool


def telegram_config_files(config_dir: Path) -> list[Path]:
    return [config_dir / ALERTS_FILE]


def load_telegram_config(config_dir: Path) -> TelegramAlertsConfig:
    """Raises ConfigLoadError on a missing file, hygiene problems or schema errors."""
    path = config_dir / ALERTS_FILE
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

    event_severity: dict[str, Severity] = {}
    for key, events in parsed.severities.items():
        severity = _SEVERITY_KEYS[key]
        for event in events:
            if event in event_severity:
                raise ConfigLoadError(
                    f"{path}: event {event!r} listed under more than one severity"
                )
            event_severity[event] = severity

    anti_spam = AntiSpamPolicy(
        cooldown_seconds=parsed.anti_spam.cooldown_seconds,
        rate_limit_per_hour=parsed.anti_spam.rate_limit_per_hour,
    )
    return TelegramAlertsConfig(
        anti_spam=anti_spam,
        event_severity=event_severity,
        send_recovery=parsed.anti_spam.send_recovery,
    )
