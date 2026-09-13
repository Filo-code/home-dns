"""Load the filtering configuration (groups, policies, sources, rules, protected domains).

File layout under the config directory (ADR 0003):

    groups/groups.yaml           groups:   [GroupDefinition]
    policies/policies.yaml       policies: [Policy]
    blocklists/sources.yaml      sources:  [BlocklistSource]
    rules/allow.yaml             rules:    [DomainRule]
    rules/deny.yaml              rules:    [DomainRule]
    rules/regex.yaml             rules:    [RegexRule]
    protected-domains/*.yaml     one ProtectedCategory per file

Every file carries ``schema_version: 1``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError

from home_dns.config.loader import ConfigLoadError, check_file_hygiene, read_yaml_mapping
from home_dns.core.filtering import (
    BlocklistSource,
    DomainRule,
    FilteringConfig,
    GroupDefinition,
    Issue,
    Policy,
    ProtectedCategory,
    RegexRule,
    check_filtering_config,
)

GROUPS_FILE = Path("groups/groups.yaml")
POLICIES_FILE = Path("policies/policies.yaml")
SOURCES_FILE = Path("blocklists/sources.yaml")
ALLOW_FILE = Path("rules/allow.yaml")
DENY_FILE = Path("rules/deny.yaml")
REGEX_FILE = Path("rules/regex.yaml")
PROTECTED_DIR = Path("protected-domains")


class _File(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1]


class _GroupsFile(_File):
    groups: tuple[GroupDefinition, ...]


class _PoliciesFile(_File):
    policies: tuple[Policy, ...]


class _SourcesFile(_File):
    sources: tuple[BlocklistSource, ...]


class _DomainRulesFile(_File):
    rules: tuple[DomainRule, ...] = ()


class _RegexRulesFile(_File):
    rules: tuple[RegexRule, ...] = ()


class _ProtectedFile(_File, ProtectedCategory):
    pass


_F = TypeVar("_F", bound=BaseModel)


@dataclass(frozen=True)
class FilteringLoadResult:
    config: FilteringConfig
    issues: tuple[Issue, ...]
    files: tuple[Path, ...]
    evaluated_at: datetime

    @property
    def errors(self) -> tuple[Issue, ...]:
        return tuple(i for i in self.issues if i.level == "error")

    @property
    def warnings(self) -> tuple[Issue, ...]:
        return tuple(i for i in self.issues if i.level == "warning")


def _format_errors(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}"
        for err in exc.errors(include_input=False, include_url=False)
    )


def _load_file(path: Path, model: type[_F]) -> _F:
    data: dict[str, Any] = read_yaml_mapping(path)
    check_file_hygiene(data, path)
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ConfigLoadError(f"{path}: {_format_errors(exc)}") from exc


def filtering_config_files(config_dir: Path) -> list[Path]:
    """Paths owned by the filtering loader (existing protected-domain files included)."""
    fixed = [GROUPS_FILE, POLICIES_FILE, SOURCES_FILE, ALLOW_FILE, DENY_FILE, REGEX_FILE]
    protected_dir = config_dir / PROTECTED_DIR
    protected = sorted(protected_dir.glob("*.yaml")) if protected_dir.is_dir() else []
    return [config_dir / p for p in fixed] + protected


def load_filtering_config(config_dir: Path, *, now: datetime) -> FilteringLoadResult:
    """Parse and cross-check the filtering configuration.

    Raises ConfigLoadError on missing files or schema errors.
    """
    groups = _load_file(config_dir / GROUPS_FILE, _GroupsFile)
    policies = _load_file(config_dir / POLICIES_FILE, _PoliciesFile)
    sources = _load_file(config_dir / SOURCES_FILE, _SourcesFile)
    allow = _load_file(config_dir / ALLOW_FILE, _DomainRulesFile)
    deny = _load_file(config_dir / DENY_FILE, _DomainRulesFile)
    regex = _load_file(config_dir / REGEX_FILE, _RegexRulesFile)

    protected_dir = config_dir / PROTECTED_DIR
    if not protected_dir.is_dir():
        raise ConfigLoadError(f"{protected_dir}: directory not found")
    protected_files = sorted(protected_dir.glob("*.yaml"))
    protected = tuple(_load_file(path, _ProtectedFile) for path in protected_files)
    for path, category in zip(protected_files, protected, strict=True):
        if category.category != path.stem:
            raise ConfigLoadError(f"{path}: category {category.category!r} must match file name")

    config = FilteringConfig(
        groups=groups.groups,
        policies=policies.policies,
        sources=sources.sources,
        allow=allow.rules,
        deny=deny.rules,
        regex=regex.rules,
        protected=tuple(
            ProtectedCategory(category=p.category, description=p.description, domains=p.domains)
            for p in protected
        ),
    )
    return FilteringLoadResult(
        config=config,
        issues=tuple(check_filtering_config(config, now=now)),
        files=tuple(filtering_config_files(config_dir)),
        evaluated_at=now,
    )
