"""Load and validate an application profile.

Loading answers "is this configuration well-formed?". Whether it is fit to run in a given
environment is answered separately by ``readiness.evaluate_readiness``.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from home_dns.config.placeholders import MalformedPlaceholderError, iter_raw_placeholders
from home_dns.config.settings import AppSettings, Environment, SecretSettings

ENV_VAR_ENVIRONMENT = "HOME_DNS_ENV"
ENV_VAR_CONFIG_DIR = "HOME_DNS_CONFIG_DIR"
APP_PROFILE_DIR = "app"

_SECRET_KEY_RE = re.compile(r"password|passwd|secret|token|api[_-]?key|private[_-]?key", re.I)


class ConfigLoadError(Exception):
    """The configuration cannot be loaded (CLI exit code 2)."""


@dataclass(frozen=True)
class LoadedConfig:
    environment: Environment
    profile_path: Path
    project_root: Path
    settings: AppSettings
    secrets: SecretSettings

    def resolve(self, path: Path) -> Path:
        """Resolve a configured path; relative paths are anchored at the project root."""
        return path if path.is_absolute() else self.project_root / path


def resolve_environment(
    explicit: str | None, environ: Mapping[str, str] = os.environ
) -> Environment:
    value = explicit or environ.get(ENV_VAR_ENVIRONMENT) or Environment.DEVELOPMENT.value
    try:
        return Environment(value)
    except ValueError:
        allowed = ", ".join(e.value for e in Environment)
        raise ConfigLoadError(f"unknown environment {value!r} (allowed: {allowed})") from None


def default_config_dir(environ: Mapping[str, str] = os.environ) -> Path:
    configured = environ.get(ENV_VAR_CONFIG_DIR)
    if configured:
        return Path(configured)
    # Source checkout layout: <root>/src/home_dns/config/loader.py -> <root>/config
    return Path(__file__).resolve().parents[3] / "config"


def read_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigLoadError(f"{path}: file not found")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigLoadError(f"{path}: invalid YAML: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigLoadError(f"{path}: top level must be a mapping")
    return data


def iter_secret_like_keys(data: Any, path: str = "") -> Iterator[str]:
    if isinstance(data, dict):
        for key, value in data.items():
            key_path = f"{path}.{key}" if path else str(key)
            if _SECRET_KEY_RE.search(str(key)):
                yield key_path
            yield from iter_secret_like_keys(value, key_path)
    elif isinstance(data, list):
        for index, value in enumerate(data):
            yield from iter_secret_like_keys(value, f"{path}[{index}]")


def check_file_hygiene(data: dict[str, Any], path: Path) -> None:
    """Reject secrets and malformed placeholders in any configuration file."""
    secret_keys = list(iter_secret_like_keys(data))
    if secret_keys:
        raise ConfigLoadError(
            f"{path}: secret-like keys are not allowed in config files "
            f"({', '.join(secret_keys)}); use HOME_DNS_* environment variables"
        )
    try:
        list(iter_raw_placeholders(data))
    except MalformedPlaceholderError as exc:
        raise ConfigLoadError(f"{path}: {exc}") from exc


def _format_validation_error(exc: ValidationError) -> str:
    parts = []
    for error in exc.errors(include_input=False, include_url=False):
        location = ".".join(str(item) for item in error["loc"]) or "<root>"
        parts.append(f"{location}: {error['msg']}")
    return "; ".join(parts)


def load_config(
    *,
    environment: Environment,
    config_dir: Path,
    profile: Path | None = None,
) -> LoadedConfig:
    profile_path = profile or config_dir / APP_PROFILE_DIR / f"{environment.value}.yaml"
    raw = read_yaml_mapping(profile_path)
    check_file_hygiene(raw, profile_path)

    declared = raw.pop("environment", None)
    if declared != environment.value:
        raise ConfigLoadError(
            f"{profile_path}: profile declares environment {declared!r} "
            f"but {environment.value!r} was selected"
        )

    try:
        settings = AppSettings(**raw)
        secrets = SecretSettings()
    except ValidationError as exc:
        raise ConfigLoadError(f"{profile_path}: {_format_validation_error(exc)}") from exc

    return LoadedConfig(
        environment=environment,
        profile_path=profile_path,
        project_root=config_dir.resolve().parent,
        settings=settings,
        secrets=secrets,
    )


@dataclass(frozen=True)
class ConfigFileScan:
    path: Path
    placeholders: tuple[str, ...] = ()
    error: str | None = None


def scan_config_tree(config_dir: Path, *, exclude: Iterable[Path] = ()) -> list[ConfigFileScan]:
    """Check YAML files under config/ that no schema owns yet, for syntax and hygiene.

    Application profiles and files in ``exclude`` (validated by their own loaders) are skipped.
    """
    results: list[ConfigFileScan] = []
    profile_dir = config_dir / APP_PROFILE_DIR
    skipped = {p.resolve() for p in exclude}
    for path in sorted([*config_dir.rglob("*.yaml"), *config_dir.rglob("*.yml")]):
        if path.is_relative_to(profile_dir) or path.resolve() in skipped:
            continue
        try:
            data = read_yaml_mapping(path)
            check_file_hygiene(data, path)
        except ConfigLoadError as exc:
            results.append(ConfigFileScan(path=path, error=str(exc)))
            continue
        tokens = tuple(f"{p}={ph.token}" for p, ph in iter_raw_placeholders(data))
        results.append(ConfigFileScan(path=path, placeholders=tokens))
    return results
