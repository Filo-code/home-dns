"""Policy engine: for group G, is domain D allowed or blocked — and why?

Pure and provider-neutral. Precedence (first match wins), mirroring Pi-hole v6 semantics:

1. protected domain                → allowed  (protected)
2. active manual allow rule        → allowed  (allow_rule)
3. active regex allow rule         → allowed  (allow_regex)
4. active manual deny rule         → blocked  (deny_rule)
5. active regex deny rule          → blocked  (deny_regex)
6. blocklist of the group's policy → blocked  (blocklist)
7. nothing matched                 → allowed  (default)
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from home_dns.core.blocklists import BlockEntry
from home_dns.core.domains import covers, normalize_domain
from home_dns.core.filtering import (
    ALL_GROUPS,
    DomainRule,
    FilteringConfig,
    RegexRule,
    RuleAction,
    RuleMetadata,
)


class Verdict(StrEnum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"


class Reason(StrEnum):
    PROTECTED = "protected"
    ALLOW_RULE = "allow_rule"
    ALLOW_REGEX = "allow_regex"
    DENY_RULE = "deny_rule"
    DENY_REGEX = "deny_regex"
    BLOCKLIST = "blocklist"
    DEFAULT = "default"


@dataclass(frozen=True)
class Decision:
    group: str
    domain: str
    verdict: Verdict
    reason: Reason
    detail: str
    matched: tuple[str, ...] = ()

    @property
    def blocked(self) -> bool:
        return self.verdict is Verdict.BLOCKED


class UnknownGroupError(ValueError):
    """The group is not defined in the filtering configuration."""


def _applies(rule: RuleMetadata, group: str, now: datetime) -> bool:
    return rule.is_active(now) and (rule.groups == (ALL_GROUPS,) or group in rule.groups)


def _names(domain: str) -> list[str]:
    """The domain itself followed by its parents (``a.b.c`` -> ``a.b.c``, ``b.c``)."""
    labels = domain.split(".")
    return [".".join(labels[i:]) for i in range(len(labels) - 1)]


class PolicyEngine:
    """Decisions for one configuration, one set of blocklist entries and one point in time."""

    def __init__(
        self,
        config: FilteringConfig,
        blocklists: Mapping[str, frozenset[BlockEntry]],
        *,
        now: datetime,
    ) -> None:
        self._config = config
        self._now = now
        self._groups = {g.id: g for g in config.groups}
        self._policies = {p.id: p for p in config.policies}
        self._protected = config.protected_domains()
        self._blocklists = blocklists
        self._regex: dict[int, re.Pattern[str]] = {
            id(rule): re.compile(rule.pattern) for rule in config.regex
        }

    def sources_for(self, group: str) -> tuple[str, ...]:
        if group not in self._groups:
            raise UnknownGroupError(f"unknown group {group!r}")
        return self._policies[self._groups[group].policy].blocklists

    def _domain_rule(
        self, rules: tuple[DomainRule, ...], group: str, name: str
    ) -> DomainRule | None:
        for rule in rules:
            if _applies(rule, group, self._now) and covers(
                rule.domain, include_subdomains=rule.include_subdomains, name=name
            ):
                return rule
        return None

    def _regex_rule(self, action: RuleAction, group: str, name: str) -> RegexRule | None:
        for rule in self._config.regex:
            if (
                rule.action is action
                and _applies(rule, group, self._now)
                and self._regex[id(rule)].search(name)
            ):
                return rule
        return None

    def decide(self, group: str, domain: str) -> Decision:
        sources = self.sources_for(group)
        name = normalize_domain(domain)

        def decision(verdict: Verdict, reason: Reason, detail: str, *matched: str) -> Decision:
            return Decision(group, name, verdict, reason, detail, tuple(matched))

        for entry in self._protected:
            if covers(entry.domain, include_subdomains=entry.include_subdomains, name=name):
                scope = "and subdomains" if entry.include_subdomains else "exact"
                return decision(
                    Verdict.ALLOWED,
                    Reason.PROTECTED,
                    f"protected {entry.domain} ({scope}): {entry.reason}",
                    entry.domain,
                )
        if rule := self._domain_rule(self._config.allow, group, name):
            return decision(
                Verdict.ALLOWED, Reason.ALLOW_RULE, f"allow rule: {rule.reason}", rule.domain
            )
        if regex := self._regex_rule(RuleAction.ALLOW, group, name):
            return decision(
                Verdict.ALLOWED, Reason.ALLOW_REGEX, f"allow regex: {regex.reason}", regex.pattern
            )
        if rule := self._domain_rule(self._config.deny, group, name):
            return decision(
                Verdict.BLOCKED, Reason.DENY_RULE, f"deny rule: {rule.reason}", rule.domain
            )
        if regex := self._regex_rule(RuleAction.DENY, group, name):
            return decision(
                Verdict.BLOCKED, Reason.DENY_REGEX, f"deny regex: {regex.reason}", regex.pattern
            )

        candidates = _names(name)
        matched_sources = []
        for source_id in sources:
            entries = self._blocklists.get(source_id, frozenset())
            if BlockEntry(name, False) in entries or any(
                BlockEntry(candidate, True) in entries for candidate in candidates
            ):
                matched_sources.append(source_id)
        if matched_sources:
            return decision(
                Verdict.BLOCKED,
                Reason.BLOCKLIST,
                f"listed by {', '.join(matched_sources)}",
                *matched_sources,
            )
        return decision(Verdict.ALLOWED, Reason.DEFAULT, "not matched by any rule or list")
