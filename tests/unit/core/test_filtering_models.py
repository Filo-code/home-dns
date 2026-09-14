from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from home_dns.core.filtering import (
    BlocklistSource,
    DomainRule,
    GroupDefinition,
    Policy,
    ProtectedDomain,
    RegexRule,
    RuleAction,
)

META: dict[str, Any] = {
    "reason": "test rule",
    "author": "tests",
    "created_at": date(2026, 9, 1),
    "groups": ["DEFAULT"],
    "source": "unit test",
}


def _domain_rule(**overrides: Any) -> DomainRule:
    return DomainRule(**{**META, "domain": "ads.example.com", **overrides})


@pytest.mark.parametrize("group_id", ["DEFAULT", "PC", "SMART-TV", "IOT", "LIVING-ROOM-2"])
def test_group_ids_accept_upper_case_words(group_id: str) -> None:
    assert GroupDefinition(id=group_id, description="d", policy="standard").id == group_id


@pytest.mark.parametrize("group_id", ["default", "Smart-TV", "SMART_TV", "-TV", "TV-", "1TV", ""])
def test_group_ids_reject_other_forms(group_id: str) -> None:
    with pytest.raises(ValidationError):
        GroupDefinition(id=group_id, description="d", policy="standard")


@pytest.mark.parametrize("policy_id", ["Standard", "standard_1", "-x", ""])
def test_policy_ids_are_slugs(policy_id: str) -> None:
    with pytest.raises(ValidationError):
        Policy(id=policy_id, description="d")


def _source(**overrides: Any) -> BlocklistSource:
    values: dict[str, Any] = {
        "id": "list-a",
        "name": "List A",
        "homepage": "https://lists.example/a",
        "license": "GPL-3.0",
        "format": "adblock",
        "categories": ["advertising"],
        "urls": {"primary": "https://cdn.example/a.txt"},
        "update_interval_hours": 24,
    }
    values.update(overrides)
    return BlocklistSource(**values)


def test_valid_source() -> None:
    source = _source(
        urls={"primary": "https://cdn.example/a.txt", "fallback": "https://mirror.example/a.txt"}
    )
    assert source.urls.fallback is not None


@pytest.mark.parametrize(
    "overrides",
    [
        {"urls": {"primary": "http://cdn.example/a.txt"}},
        {"urls": {"primary": "https://cdn.example/a.txt", "fallback": "http://m.example/a.txt"}},
        {"urls": {"primary": "https://cdn.example/a.txt", "fallback": "https://cdn.example/a.txt"}},
        {"homepage": "ftp://lists.example"},
        {"categories": []},
        {"categories": ["crypto"]},
        {"format": "dnsmasq"},
        {"update_interval_hours": 0},
        {"update_interval_hours": 169},
        {"unexpected": True},
    ],
)
def test_invalid_sources_are_rejected(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _source(**overrides)


def test_domain_rule_normalizes_domain_and_supports_expiry() -> None:
    rule = _domain_rule(domain="Ads.Example.COM.", expires_at="2026-09-20T00:00:00+02:00")
    assert rule.domain == "ads.example.com"
    assert rule.is_active(datetime(2026, 9, 19, 21, 59, tzinfo=UTC))
    assert not rule.is_active(datetime(2026, 9, 19, 22, 0, tzinfo=UTC))


def test_rule_without_expiry_is_always_active() -> None:
    assert _domain_rule().is_active(datetime(2099, 1, 1, tzinfo=UTC))


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"expires_at": datetime(2026, 9, 20)}, "timezone"),
        ({"expires_at": "2026-08-31T23:00:00+00:00"}, "after created_at"),
        ({"created_at": datetime(2026, 9, 1, tzinfo=UTC)}, "must be a date"),
        ({"groups": []}, "at least 1"),
        ({"groups": ["*", "PC"]}, "only entry"),
        ({"groups": ["PC", "PC"]}, "duplicates"),
        ({"groups": ["pc"]}, "upper-case"),
        ({"reason": "no"}, "at least 3"),
        ({"author": ""}, "at least 1"),
        ({"source": ""}, "at least 1"),
        ({"domain": "*.example.com"}, "wildcards"),
        ({"domain": "192.0.2.1"}, "IP addresses"),
    ],
)
def test_invalid_rule_metadata(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        _domain_rule(**overrides)


def test_metadata_fields_are_required() -> None:
    for field in ("reason", "author", "created_at", "groups", "source"):
        values = {**META, "domain": "ads.example.com"}
        del values[field]
        with pytest.raises(ValidationError, match=field):
            DomainRule(**values)


def test_all_groups_sentinel() -> None:
    assert _domain_rule(groups=["*"]).applies_to_all_groups()
    assert not _domain_rule(groups=["PC"]).applies_to_all_groups()


def test_regex_rule_validation() -> None:
    rule = RegexRule(**META, action="deny", pattern=r"^ads?[0-9]*\.example\.com$")
    assert rule.action is RuleAction.DENY
    for pattern, message in [
        ("(unclosed", "unbalanced"),
        (".*", "empty string"),
        ("x" * 513, "at most 512"),
    ]:
        with pytest.raises(ValidationError, match=message):
            RegexRule(**META, action="deny", pattern=pattern)
    with pytest.raises(ValidationError):
        RegexRule(**META, action="block", pattern="^x$")


def test_protected_domain_defaults_to_subdomains() -> None:
    entry = ProtectedDomain(domain="GoogleVideo.example", reason="video CDN", source="test")
    assert entry.domain == "googlevideo.example"
    assert entry.include_subdomains is True
