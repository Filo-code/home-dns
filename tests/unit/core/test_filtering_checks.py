from datetime import UTC, date, datetime
from typing import Any

from home_dns.core.filtering import (
    BlocklistSource,
    DomainRule,
    FilteringConfig,
    GroupDefinition,
    Issue,
    Policy,
    ProtectedCategory,
    ProtectedDomain,
    RegexRule,
    check_filtering_config,
)

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
META: dict[str, Any] = {
    "reason": "test rule",
    "author": "tests",
    "created_at": date(2026, 9, 1),
    "source": "unit test",
}


def _source(source_id: str) -> BlocklistSource:
    return BlocklistSource(
        id=source_id,
        name=source_id,
        homepage="https://lists.example",
        license="GPL-3.0",
        format="adblock",
        categories=["malware"],
        urls={"primary": f"https://cdn.example/{source_id}.txt"},
        update_interval_hours=24,
    )


def _rule(domain: str, groups: list[str], **extra: Any) -> DomainRule:
    return DomainRule(**{**META, **extra, "domain": domain, "groups": groups})


PROTECTED = (
    ProtectedCategory(
        category="technology",
        description="tech",
        domains=(ProtectedDomain(domain="video.example", reason="video CDN", source="t"),),
    ),
)


def _config(**overrides: Any) -> FilteringConfig:
    values: dict[str, Any] = {
        "groups": (
            GroupDefinition(id="DEFAULT", description="d", policy="standard"),
            GroupDefinition(id="SMART-TV", description="tv", policy="conservative"),
        ),
        "policies": (
            Policy(id="standard", description="s", blocklists=("list-a", "list-b")),
            Policy(id="conservative", description="c", blocklists=("list-b",)),
        ),
        "sources": (_source("list-a"), _source("list-b")),
        "protected": PROTECTED,
    }
    values.update(overrides)
    return FilteringConfig(**values)


def _errors(issues: list[Issue]) -> list[str]:
    return [f"{i.location}: {i.message}" for i in issues if i.level == "error"]


def test_valid_config_has_no_errors_or_warnings() -> None:
    issues = check_filtering_config(_config(), now=NOW)
    assert [i for i in issues if i.level != "info"] == []


def test_adding_a_group_needs_only_configuration() -> None:
    config = _config(
        groups=(
            *_config().groups,
            GroupDefinition(id="IOT", description="iot", policy="conservative"),
        ),
        allow=(_rule("updates.example", ["IOT"]),),
    )
    assert _errors(check_filtering_config(config, now=NOW)) == []


def test_default_group_is_required() -> None:
    config = _config(groups=(GroupDefinition(id="PC", description="pc", policy="standard"),))
    assert "groups: the DEFAULT group is required" in _errors(
        check_filtering_config(config, now=NOW)
    )


def test_unknown_references_are_errors() -> None:
    config = _config(
        groups=(GroupDefinition(id="DEFAULT", description="d", policy="missing"),),
        policies=(Policy(id="standard", description="s", blocklists=("nope", "list-a", "list-a")),),
        deny=(_rule("ads.example", ["GHOST"]),),
    )
    errors = _errors(check_filtering_config(config, now=NOW))
    assert "group:DEFAULT: unknown policy 'missing'" in errors
    assert "policy:standard: unknown blocklist 'nope'" in errors
    assert "policy:standard: blocklists contains duplicates" in errors
    assert "deny[0]: unknown group 'GHOST'" in errors


def test_duplicate_ids_are_errors() -> None:
    base = _config()
    config = _config(
        groups=(*base.groups, base.groups[0]),
        policies=(*base.policies, base.policies[0]),
        sources=(*base.sources, base.sources[0]),
        protected=(*PROTECTED, PROTECTED[0]),
    )
    errors = _errors(check_filtering_config(config, now=NOW))
    for expected in (
        "group:DEFAULT: duplicate group id",
        "policy:standard: duplicate policy id",
        "source:list-a: duplicate source id",
        "protected-category:technology: duplicate protected-category id",
        "protected:video.example: listed more than once",
    ):
        assert expected in errors


def test_unused_policies_and_sources_are_informational() -> None:
    config = _config(
        policies=(*_config().policies, Policy(id="spare", description="x")),
        sources=(*_config().sources, _source("list-c")),
    )
    infos = {
        (i.location, i.message)
        for i in check_filtering_config(config, now=NOW)
        if i.level == "info"
    }
    assert ("policy:spare", "not used by any group") in infos
    assert ("source:list-c", "not used by any policy") in infos


def test_duplicate_and_conflicting_rules_for_overlapping_groups() -> None:
    config = _config(
        allow=(_rule("cdn.example", ["SMART-TV"]), _rule("cdn.example", ["*"])),
        deny=(_rule("cdn.example", ["SMART-TV"]), _rule("track.example", ["DEFAULT"])),
    )
    errors = _errors(check_filtering_config(config, now=NOW))
    assert "allow[1]: duplicates allow[0] (cdn.example) for overlapping groups" in errors
    assert "deny[0]: conflicts with allow[0] (cdn.example) for overlapping groups" in errors


def test_same_domain_for_disjoint_groups_is_allowed() -> None:
    config = _config(
        allow=(_rule("cdn.example", ["SMART-TV"]),),
        deny=(_rule("cdn.example", ["DEFAULT"]),),
    )
    assert _errors(check_filtering_config(config, now=NOW)) == []


def test_exact_and_subdomain_rules_for_same_domain_do_not_conflict() -> None:
    config = _config(
        allow=(_rule("cdn.example", ["*"]),),
        deny=(_rule("cdn.example", ["*"], include_subdomains=True),),
    )
    assert _errors(check_filtering_config(config, now=NOW)) == []


def test_expired_rules_are_inactive_and_reported() -> None:
    expired = _rule("cdn.example", ["SMART-TV"], expires_at=datetime(2026, 9, 10, tzinfo=UTC))
    active = _rule("cdn.example", ["SMART-TV"], expires_at=datetime(2026, 9, 20, tzinfo=UTC))
    config = _config(allow=(expired,), deny=(_rule("cdn.example", ["SMART-TV"]),))
    issues = check_filtering_config(config, now=NOW)
    assert _errors(issues) == []
    assert any(
        i.level == "info" and i.location == "allow[0]" and "expired at" in i.message for i in issues
    )
    conflicting = _config(allow=(active,), deny=(_rule("cdn.example", ["SMART-TV"]),))
    assert _errors(check_filtering_config(conflicting, now=NOW))


def test_seven_day_smart_tv_exception_expires_automatically() -> None:
    rule = _rule(
        "tvstore.example",
        ["SMART-TV"],
        created_at=date(2026, 9, 13),
        expires_at=datetime(2026, 9, 20, 12, 0, tzinfo=UTC),
    )
    config = _config(allow=(rule,))
    assert rule.is_active(NOW)
    later = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
    assert not rule.is_active(later)
    assert any("expired" in i.message for i in check_filtering_config(config, now=later))


def test_deny_rules_may_not_touch_protected_domains() -> None:
    config = _config(
        deny=(
            _rule("video.example", ["DEFAULT"]),
            _rule("edge.video.example", ["DEFAULT"]),
            _rule("parent.example", ["DEFAULT"], include_subdomains=True),
        ),
        protected=(
            *PROTECTED,
            ProtectedCategory(
                category="infra",
                description="i",
                domains=(
                    ProtectedDomain(
                        domain="auth.parent.example",
                        include_subdomains=False,
                        reason="login",
                        source="t",
                    ),
                ),
            ),
        ),
    )
    errors = _errors(check_filtering_config(config, now=NOW))
    assert "deny[0]: would block protected domain video.example" in errors
    assert "deny[1]: would block protected domain video.example" in errors
    assert "deny[2]: would block protected domain auth.parent.example" in errors


def test_regex_rules_checked_against_protected_domains_and_duplicates() -> None:
    config = _config(
        regex=(
            RegexRule(**META, groups=["*"], action="deny", pattern=r"^video\."),
            RegexRule(**META, groups=["*"], action="allow", pattern=r"^video\."),
            RegexRule(**META, groups=["DEFAULT"], action="deny", pattern=r"^ads\."),
            RegexRule(**META, groups=["*"], action="deny", pattern=r"^ads\."),
        )
    )
    errors = _errors(check_filtering_config(config, now=NOW))
    assert "regex[0]: pattern matches protected domain video.example" in errors
    assert "regex[1]: same pattern as regex[0] for overlapping groups" in errors
    assert "regex[3]: same pattern as regex[2] for overlapping groups" in errors
    assert not any(e.startswith("regex[1]: pattern matches") for e in errors)


def test_empty_protected_set_is_a_warning() -> None:
    issues = check_filtering_config(_config(protected=()), now=NOW)
    assert any(i.level == "warning" and i.location == "protected-domains" for i in issues)
