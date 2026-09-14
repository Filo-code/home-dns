"""Load config/storage/storage.yaml (ADR 0007, A4), the same pattern as config/filtering.py:
one schema-owning loader per config file, reusing the A0 hygiene checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from home_dns.config.loader import ConfigLoadError, check_file_hygiene, read_yaml_mapping
from home_dns.core.storage import RetentionPolicy, StorageThresholds

STORAGE_FILE = Path("storage/storage.yaml")


class _File(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1]
    disk_usage_thresholds_percent: StorageThresholds
    retention: RetentionPolicy


@dataclass(frozen=True)
class StorageConfig:
    thresholds: StorageThresholds
    retention: RetentionPolicy


def storage_config_files(config_dir: Path) -> list[Path]:
    return [config_dir / STORAGE_FILE]


def load_storage_config(config_dir: Path) -> StorageConfig:
    """Raises ConfigLoadError on a missing file, hygiene problems or schema errors."""
    path = config_dir / STORAGE_FILE
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
    return StorageConfig(
        thresholds=parsed.disk_usage_thresholds_percent, retention=parsed.retention
    )
