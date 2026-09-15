"""Load config/anomaly-detection/anomaly-detection.yaml, the same pattern as config/monitoring.py.

Every number is a threshold, never a constant baked into core/anomaly.py — this is the file an
operator edits to make a device group more or less sensitive.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from home_dns.config.loader import ConfigLoadError, check_file_hygiene, read_yaml_mapping
from home_dns.core.anomaly import AnalyzerConfig, AnomalyThresholds

ANOMALY_FILE = Path("anomaly-detection/anomaly-detection.yaml")
DEFAULT_GROUP = "DEFAULT"


class _File(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1]
    enabled: bool
    window_minutes: int
    max_entries_per_device: int
    retention_days: int
    default: AnomalyThresholds
    overrides: dict[str, AnomalyThresholds] = {}

    @model_validator(mode="after")
    def _default_group_not_duplicated_in_overrides(self) -> _File:
        if DEFAULT_GROUP in self.overrides:
            raise ValueError(
                f"overrides.{DEFAULT_GROUP} duplicates 'default'; edit 'default' instead"
            )
        return self


@dataclass(frozen=True)
class AnomalyDetectionConfig:
    enabled: bool
    retention_days: int
    analyzer: AnalyzerConfig


def anomaly_config_files(config_dir: Path) -> list[Path]:
    return [config_dir / ANOMALY_FILE]


def load_anomaly_config(config_dir: Path) -> AnomalyDetectionConfig:
    """Raises ConfigLoadError on a missing file, hygiene problems or schema errors."""
    path = config_dir / ANOMALY_FILE
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
    thresholds_by_group = {DEFAULT_GROUP: parsed.default, **parsed.overrides}
    return AnomalyDetectionConfig(
        enabled=parsed.enabled,
        retention_days=parsed.retention_days,
        analyzer=AnalyzerConfig(
            window_minutes=parsed.window_minutes,
            max_entries_per_device=parsed.max_entries_per_device,
            default_group=DEFAULT_GROUP,
            thresholds_by_group=thresholds_by_group,
        ),
    )
