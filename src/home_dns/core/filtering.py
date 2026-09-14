"""Provider-neutral filtering configuration: groups, policies, rules, protected domains and
blocklist sources, plus the cross-reference checks that tie them together.

Hard errors are returned as issues (never silently ignored) so the caller decides how to
report them. Expiring rules are evaluated against an injected ``now``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from enum import StrEnum
from itertools import combinations
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)

from home_dns.core.domains import covers, normalize_domain
from home_dns.core.regex import UnportableRegexError, validate_portable_regex

DEFAULT_GROUP = "DEFAULT"
ALL_GROUPS = "*"
MAX_REGEX_LENGTH = 512

_GROUP_ID_RE = re.compile(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*")
_SLUG_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")


def _group_id(value: str) -> str:
    if not _GROUP_ID_RE.fullmatch(value):
        raise ValueError(f"{value!r}: group ids are upper-case words joined by '-', e.g. SMART-TV")
    return value


def _slug(value: str) -> str:
    if not _SLUG_RE.fullmatch(value):
        raise ValueError(f"{value!r}: ids are lower-case words joined by '-'")
    return value


GroupId = Annotated[str, AfterValidator(_group_id)]
Slug = Annotated[str, AfterValidator(_slug)]
DomainName = Annotated[str, AfterValidator(normalize_domain)]
NonEmptyText = Annotated[str, Field(min_length=1)]


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Category(StrEnum):
    ADVERTISING = "advertising"
    TRACKING = "tracking"
    TELEMETRY = "telemetry"
    MALWARE = "malware"
    PHISHING = "phishing"
    GAMBLING = "gambling"
    ADULT = "adult"


class ListFormat(StrEnum):
    ADBLOCK = "adblock"
    HOSTS = "hosts"
    DOMAINS = "domains"


class RuleAction(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


# ---------------------------------------------------------------------------- groups/policies


class GroupDefinition(_Model):
    id: GroupId
    description: NonEmptyText
    policy: Slug


class Policy(_Model):
    id: Slug
    description: NonEmptyText
    blocklists: tuple[Slug, ...] = ()


# ------------------------------------------------------------------------------- sources


def _https(url: HttpUrl) -> HttpUrl:
    if url.scheme != "https":
        raise ValueError("blocklist URLs must use https")
    return url


SecureUrl = Annotated[HttpUrl, AfterValidator(_https)]


class SourceUrls(_Model):
    primary: SecureUrl
    fallback: SecureUrl | None = None

    @model_validator(mode="after")
    def _distinct(self) -> SourceUrls:
        if self.fallback is not None and self.fallback == self.primary:
            raise ValueError("fallback URL must differ from primary")
        return self


class SanityLimits(_Model):
    """Evidence-based limits per source. Every field is optional until approved by the owner.

    Exceeding a limit is an anomaly that holds the update for review; it is not a hard failure.
    """

    min_entries: int | None = Field(default=None, ge=1)
    max_entries: int | None = Field(default=None, ge=1)
    max_added_ratio: float | None = Field(default=None, gt=0)
    max_removed_ratio: float | None = Field(default=None, gt=0, le=1)

    @model_validator(mode="after")
    def _ordered(self) -> SanityLimits:
        if self.min_entries and self.max_entries and self.min_entries > self.max_entries:
            raise ValueError("min_entries cannot exceed max_entries")
        return self


class BlocklistSource(_Model):
    id: Slug
    name: NonEmptyText
    homepage: SecureUrl
    license: NonEmptyText
    format: ListFormat
    categories: tuple[Category, ...] = Field(min_length=1)
    urls: SourceUrls
    update_interval_hours: int = Field(ge=1, le=168)
    max_age_hours: int | None = Field(default=None, ge=1, le=720)
    sanity: SanityLimits | None = None


# --------------------------------------------------------------------------------- rules


class RuleMetadata(_Model):
    reason: str = Field(min_length=3)
    author: NonEmptyText
    created_at: date
    groups: tuple[str, ...] = Field(min_length=1)
    source: NonEmptyText
    expires_at: datetime | None = None

    @field_validator("created_at", mode="before")
    @classmethod
    def _date_only(cls, value: object) -> object:
        if isinstance(value, datetime):
            raise ValueError("created_at must be a date (YYYY-MM-DD)")
        return value

    @field_validator("expires_at")
    @classmethod
    def _aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("expires_at must include a timezone, e.g. 2026-09-20T00:00:00+02:00")
        return value

    @field_validator("groups")
    @classmethod
    def _groups(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if ALL_GROUPS in value:
            if len(value) != 1:
                raise ValueError(f"'{ALL_GROUPS}' must be the only entry in groups")
            return value
        if len(set(value)) != len(value):
            raise ValueError("groups contains duplicates")
        for group in value:
            _group_id(group)
        return value

    @model_validator(mode="after")
    def _expiry_after_creation(self) -> RuleMetadata:
        created = datetime.combine(self.created_at, time.min, tzinfo=UTC)
        if self.expires_at is not None and self.expires_at <= created:
            raise ValueError("expires_at must be after created_at")
        return self

    def is_active(self, now: datetime) -> bool:
        return self.expires_at is None or now < self.expires_at

    def applies_to_all_groups(self) -> bool:
        return self.groups == (ALL_GROUPS,)


class DomainRule(RuleMetadata):
    domain: DomainName
    include_subdomains: bool = False


class RegexRule(RuleMetadata):
    action: RuleAction
    pattern: str = Field(min_length=1, max_length=MAX_REGEX_LENGTH)

    @field_validator("pattern")
    @classmethod
    def _portable_and_selective(cls, value: str) -> str:
        try:
            validate_portable_regex(value)
        except UnportableRegexError as exc:
            raise ValueError(str(exc)) from exc
        return value


class ProtectedDomain(_Model):
    domain: DomainName
    include_subdomains: bool = True
    reason: str = Field(min_length=3)
    source: NonEmptyText


class ProtectedCategory(_Model):
    category: Slug
    description: NonEmptyText
    domains: tuple[ProtectedDomain, ...] = ()


# -------------------------------------------------------------------------------- checks


@dataclass(frozen=True)
class Issue:
    level: Literal["error", "warning", "info"]
    location: str
    message: str


class FilteringConfig(_Model):
    groups: tuple[GroupDefinition, ...]
    policies: tuple[Policy, ...]
    sources: tuple[BlocklistSource, ...]
    allow: tuple[DomainRule, ...] = ()
    deny: tuple[DomainRule, ...] = ()
    regex: tuple[RegexRule, ...] = ()
    protected: tuple[ProtectedCategory, ...] = ()

    def group_ids(self) -> set[str]:
        return {group.id for group in self.groups}

    def protected_domains(self) -> list[ProtectedDomain]:
        return [entry for category in self.protected for entry in category.domains]


def _groups_overlap(a: RuleMetadata, b: RuleMetadata) -> bool:
    return (
        a.applies_to_all_groups()
        or b.applies_to_all_groups()
        or bool(set(a.groups) & set(b.groups))
    )


def _duplicates(ids: Iterable[str], kind: str) -> list[Issue]:
    seen: set[str] = set()
    issues = []
    for identifier in ids:
        if identifier in seen:
            issues.append(Issue("error", f"{kind}:{identifier}", f"duplicate {kind} id"))
        seen.add(identifier)
    return issues


def check_filtering_config(config: FilteringConfig, *, now: datetime) -> list[Issue]:
    """Cross-reference and consistency checks.

    Locations are logical: ``group:PC``, ``policy:standard``, ``allow[3]`` (index into the
    allow rules), ``deny[0]``, ``regex[1]``, ``protected:example.com``.
    """
    issues: list[Issue] = []
    issues += _duplicates((g.id for g in config.groups), "group")
    issues += _duplicates((p.id for p in config.policies), "policy")
    issues += _duplicates((s.id for s in config.sources), "source")
    issues += _duplicates((c.category for c in config.protected), "protected-category")

    group_ids = config.group_ids()
    policy_ids = {p.id for p in config.policies}
    source_ids = {s.id for s in config.sources}

    if DEFAULT_GROUP not in group_ids:
        issues.append(Issue("error", "groups", f"the {DEFAULT_GROUP} group is required"))
    for group in config.groups:
        if group.policy not in policy_ids:
            issues.append(Issue("error", f"group:{group.id}", f"unknown policy {group.policy!r}"))
    for policy in config.policies:
        for source_ref in policy.blocklists:
            if source_ref not in source_ids:
                issues.append(
                    Issue("error", f"policy:{policy.id}", f"unknown blocklist {source_ref!r}")
                )
        if len(set(policy.blocklists)) != len(policy.blocklists):
            issues.append(Issue("error", f"policy:{policy.id}", "blocklists contains duplicates"))

    used_policies = {g.policy for g in config.groups}
    for policy in config.policies:
        if policy.id not in used_policies:
            issues.append(Issue("info", f"policy:{policy.id}", "not used by any group"))
    used_sources = {s for p in config.policies for s in p.blocklists}
    for source in config.sources:
        if source.id not in used_sources:
            issues.append(Issue("info", f"source:{source.id}", "not used by any policy"))

    all_rules: list[tuple[str, RuleMetadata]] = [
        *((f"allow[{i}]", r) for i, r in enumerate(config.allow)),
        *((f"deny[{i}]", r) for i, r in enumerate(config.deny)),
        *((f"regex[{i}]", r) for i, r in enumerate(config.regex)),
    ]
    for fallback, rule in all_rules:
        for group_ref in rule.groups:
            if group_ref != ALL_GROUPS and group_ref not in group_ids:
                issues.append(Issue("error", fallback, f"unknown group {group_ref!r}"))
        if not rule.is_active(now):
            issues.append(
                Issue(
                    "info",
                    fallback,
                    f"expired at {rule.expires_at.isoformat() if rule.expires_at else ''}; "
                    "inactive, remove when convenient",
                )
            )

    active_allow = [(i, r) for i, r in enumerate(config.allow) if r.is_active(now)]
    active_deny = [(i, r) for i, r in enumerate(config.deny) if r.is_active(now)]

    for label, rules in (("allow", active_allow), ("deny", active_deny)):
        for (i, a), (j, b) in combinations(rules, 2):
            if (
                a.domain == b.domain
                and a.include_subdomains == b.include_subdomains
                and _groups_overlap(a, b)
            ):
                issues.append(
                    Issue(
                        "error",
                        f"{label}[{j}]",
                        f"duplicates {label}[{i}] ({a.domain}) for overlapping groups",
                    )
                )

    for i, a in active_allow:
        for j, d in active_deny:
            if (
                a.domain == d.domain
                and a.include_subdomains == d.include_subdomains
                and _groups_overlap(a, d)
            ):
                issues.append(
                    Issue(
                        "error",
                        f"deny[{j}]",
                        f"conflicts with allow[{i}] ({a.domain}) for overlapping groups",
                    )
                )

    active_regex = [(i, r) for i, r in enumerate(config.regex) if r.is_active(now)]
    for (i, first), (j, second) in combinations(active_regex, 2):
        if first.pattern == second.pattern and _groups_overlap(first, second):
            issues.append(
                Issue("error", f"regex[{j}]", f"same pattern as regex[{i}] for overlapping groups")
            )

    protected = config.protected_domains()
    if not protected:
        issues.append(
            Issue(
                "warning",
                "protected-domains",
                "no protected domains defined; the blocklist tripwire has nothing to check",
            )
        )
    seen_protected: set[tuple[str, bool]] = set()
    for entry in protected:
        key = (entry.domain, entry.include_subdomains)
        if key in seen_protected:
            issues.append(Issue("error", f"protected:{entry.domain}", "listed more than once"))
        seen_protected.add(key)

    for j, rule in active_deny:
        for entry in protected:
            hits = covers(
                rule.domain, include_subdomains=rule.include_subdomains, name=entry.domain
            ) or covers(entry.domain, include_subdomains=entry.include_subdomains, name=rule.domain)
            if hits:
                issues.append(
                    Issue("error", f"deny[{j}]", f"would block protected domain {entry.domain}")
                )
    for j, regex_rule in active_regex:
        if regex_rule.action is not RuleAction.DENY:
            continue
        compiled = re.compile(regex_rule.pattern)
        for entry in protected:
            if compiled.search(entry.domain):
                issues.append(
                    Issue(
                        "error", f"regex[{j}]", f"pattern matches protected domain {entry.domain}"
                    )
                )
    return issues
