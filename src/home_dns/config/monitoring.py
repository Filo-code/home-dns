"""Load config/monitoring/monitoring.yaml (A5), the same pattern as config/storage.py."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from home_dns.config.loader import ConfigLoadError, check_file_hygiene, read_yaml_mapping
from home_dns.core.monitoring import BackoffPolicy, IncidentPolicy

MONITORING_FILE = Path("monitoring/monitoring.yaml")


class _File(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1]
    incident: IncidentPolicy
    restart_budget: BackoffPolicy


@dataclass(frozen=True)
class MonitoringConfig:
    incident: IncidentPolicy
    restart_budget: BackoffPolicy


def monitoring_config_files(config_dir: Path) -> list[Path]:
    return [config_dir / MONITORING_FILE]


def load_monitoring_config(config_dir: Path) -> MonitoringConfig:
    """Raises ConfigLoadError on a missing file, hygiene problems or schema errors."""
    path = config_dir / MONITORING_FILE
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
    return MonitoringConfig(incident=parsed.incident, restart_budget=parsed.restart_budget)
