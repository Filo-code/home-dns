from datetime import UTC, date, datetime
from typing import Any

import pytest

from home_dns.core.blocklists import BlockEntry
from home_dns.core.domains import InvalidDomainError
from home_dns.core.filtering import (
    BlocklistSource,
    DomainRule,
    FilteringConfig,
    GroupDefinition,
    Policy,
    ProtectedCategory,
    ProtectedDomain,
    RegexRule,
)
from home_dns.core.policy import PolicyEngine, Reason, UnknownGroupError, Verdict

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
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
        categories=["advertising"],
        urls={"primary": f"https://cdn.example/{source_id}.txt"},
        update_interval_hours=24,
    )


def _config(**overrides: Any) -> FilteringConfig:
    values: dict[str, Any] = {
        "groups": (
            GroupDefinition(id="DEFAULT", description="d", policy="strict"),
            GroupDefinition(id="SMART-TV", description="tv", policy="light"),
        ),
        "policies": (
            Policy(id="strict", description="s", blocklists=("big", "threats")),
            Policy(id="light", description="l", blocklists=("small", "threats")),
        ),
        "sources": (_source("big"), _source("small"), _source("threats")),
        "protected": (
            ProtectedCategory(
                category="streaming",
                description="s",
                domains=(
                    ProtectedDomain(
                        domain="video.example",
                        include_subdomains=True,
                        reason="video CDN",
                        source="t",
                    ),
                    ProtectedDomain(
                        domain="brand.example",
                        include_subdomains=False,
                        reason="brand apex",
                        source="t",
                    ),
                ),
            ),
        ),
    }
    values.update(overrides)
    return FilteringConfig(**values)


LISTS = {
    "big": frozenset(
        {
            BlockEntry("ads.example", True),
            BlockEntry("tracker.example", True),
            BlockEntry("video.example", True),
            BlockEntry("brand.example", True),
        }
    ),
    "small": frozenset({BlockEntry("ads.example", True), BlockEntry("exact-only.example", False)}),
    "threats": frozenset({BlockEntry("malware.example", True)}),
}


def _engine(**config: Any) -> PolicyEngine:
    return PolicyEngine(_config(**config), LISTS, now=NOW)


def test_group_lists_decide_blocking() -> None:
    engine = _engine()
    assert engine.decide("DEFAULT", "tracker.example").reason is Reason.BLOCKLIST
    assert engine.decide("SMART-TV", "sub.tracker.example").verdict is Verdict.ALLOWED
    assert engine.decide("SMART-TV", "sub.ads.example").matched == ("small",)
    assert engine.decide("DEFAULT", "sub.ads.example").matched == ("big",)


def test_threat_lists_apply_to_every_group() -> None:
    engine = _engine()
    for group in ("DEFAULT", "SMART-TV"):
        assert engine.decide(group, "c2.malware.example").blocked


def test_exact_list_entries_do_not_cover_subdomains() -> None:
    engine = _engine()
    assert engine.decide("SMART-TV", "exact-only.example").blocked
    assert not engine.decide("SMART-TV", "sub.exact-only.example").blocked


def test_protected_subtree_beats_covering_list_entries() -> None:
    engine = _engine()
    decision = engine.decide("DEFAULT", "edge-1.video.example")
    assert decision.verdict is Verdict.ALLOWED and decision.reason is Reason.PROTECTED
    assert decision.matched == ("video.example",)
    assert "and subdomains" in decision.detail


def test_protected_exact_entry_covers_only_itself() -> None:
    engine = _engine()
    assert engine.decide("DEFAULT", "brand.example").reason is Reason.PROTECTED
    tracking = engine.decide("DEFAULT", "metrics.brand.example")
    assert tracking.blocked and tracking.reason is Reason.BLOCKLIST  # covered by ||brand.example^


def test_default_allow_and_normalization() -> None:
    engine = _engine()
    decision = engine.decide("SMART-TV", "Unlisted.Example.NET.")
    assert decision.domain == "unlisted.example.net"
    assert decision.reason is Reason.DEFAULT and not decision.blocked


def test_precedence_allow_rule_beats_deny_and_lists() -> None:
    engine = _engine(
        allow=(
            DomainRule(**META, domain="ads.example", include_subdomains=True, groups=["SMART-TV"]),
        ),
        deny=(DomainRule(**META, domain="ads.example", groups=["DEFAULT"]),),
    )
    assert engine.decide("SMART-TV", "cdn.ads.example").reason is Reason.ALLOW_RULE
    assert engine.decide("DEFAULT", "ads.example").reason is Reason.DENY_RULE


def test_precedence_order_across_all_layers() -> None:
    engine = _engine(
        allow=(DomainRule(**META, domain="layers.example", groups=["*"]),),
        deny=(DomainRule(**META, domain="deny.example", include_subdomains=True, groups=["*"]),),
        regex=(
            RegexRule(**META, action="allow", pattern=r"^ok\.deny\.example$", groups=["*"]),
            RegexRule(**META, action="deny", pattern=r"^regex-[0-9]+\.example$", groups=["*"]),
            RegexRule(**META, action="deny", pattern=r"^layers\.example$", groups=["*"]),
        ),
    )
    assert engine.decide("DEFAULT", "layers.example").reason is Reason.ALLOW_RULE
    assert engine.decide("DEFAULT", "ok.deny.example").reason is Reason.ALLOW_REGEX
    assert engine.decide("DEFAULT", "x.deny.example").reason is Reason.DENY_RULE
    assert engine.decide("DEFAULT", "regex-42.example").reason is Reason.DENY_REGEX
    assert engine.decide("DEFAULT", "edge.video.example").reason is Reason.PROTECTED


def test_protected_beats_allow_and_deny_rules_that_escape_validation() -> None:
    engine = _engine(
        deny=(DomainRule(**META, domain="video.example", include_subdomains=True, groups=["*"]),),
        regex=(RegexRule(**META, action="deny", pattern=r"video", groups=["*"]),),
    )
    assert engine.decide("SMART-TV", "a.video.example").reason is Reason.PROTECTED


def test_rules_respect_group_scope_and_expiry() -> None:
    expired = DomainRule(
        **META,
        domain="tvstore.example",
        groups=["SMART-TV"],
        expires_at=datetime(2026, 9, 10, tzinfo=UTC),
    )
    active = DomainRule(
        **META,
        domain="ads.example",
        groups=["SMART-TV"],
        expires_at=datetime(2026, 9, 21, tzinfo=UTC),
    )
    engine = _engine(
        allow=(expired, active), deny=(DomainRule(**META, domain="tvstore.example", groups=["*"]),)
    )
    assert engine.decide("SMART-TV", "tvstore.example").reason is Reason.DENY_RULE
    assert engine.decide("SMART-TV", "ads.example").reason is Reason.ALLOW_RULE
    assert engine.decide("DEFAULT", "ads.example").reason is Reason.BLOCKLIST
    later = PolicyEngine(_config(allow=(active,)), LISTS, now=datetime(2026, 9, 21, tzinfo=UTC))
    assert later.decide("SMART-TV", "ads.example").reason is Reason.BLOCKLIST


def test_missing_blocklist_artifact_means_not_evaluated_not_blocked() -> None:
    engine = PolicyEngine(_config(), {}, now=NOW)
    assert engine.decide("DEFAULT", "tracker.example").reason is Reason.DEFAULT


def test_unknown_group_and_invalid_domain() -> None:
    engine = _engine()
    with pytest.raises(UnknownGroupError):
        engine.decide("GUEST", "a.example")
    with pytest.raises(UnknownGroupError):
        engine.sources_for("IOT")
    with pytest.raises(InvalidDomainError):
        engine.decide("DEFAULT", "*.example")
