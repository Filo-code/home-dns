"""Regression tests for the committed A3 policy (config/), fully offline.

A *hostile* synthetic blocklist blocks every catalogued endpoint and all of its parents, simulating
the worst possible upstream list. Required endpoints must still be allowed for every group; that
guarantee must hold independently of what real lists contain.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from home_dns.config.filtering import load_filtering_config
from home_dns.core.blocklists import BlockEntry, find_tripwire_hits
from home_dns.core.domains import normalize_domain
from home_dns.core.filtering import FilteringConfig
from home_dns.core.policy import PolicyEngine, Reason

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
REPO = Path(__file__).resolve().parents[3]
CATALOG: dict[str, Any] = yaml.safe_load(
    (REPO / "tests" / "data" / "compatibility.yaml").read_text()
)
GROUPS = ["DEFAULT", "PC", "GAMING", "MOBILE", "SMART-TV", "XBOX"]
MULTI_TENANT_APEXES = {
    "cloudfront.net",
    "akamaized.net",
    "akamaihd.net",
    "akamaiedge.net",
    "edgekey.net",
    "edgesuite.net",
    "fastly.net",
    "azureedge.net",
    "azurefd.net",
    "blob.core.windows.net",
    "trafficmanager.net",
    "amazonaws.com",
    "googleusercontent.com",
    "cloudflare.net",
    "googleapis.com",
}


@pytest.fixture(scope="module")
def config() -> FilteringConfig:
    return load_filtering_config(REPO / "config", now=NOW).config


def _parents(name: str) -> list[str]:
    labels = name.split(".")
    return [".".join(labels[i:]) for i in range(len(labels) - 1)]


def _hostile(config: FilteringConfig) -> dict[str, frozenset[BlockEntry]]:
    names = {n for s in CATALOG["services"] for n in s["required"]} | set(
        CATALOG["must_stay_blockable"]
    )
    entries = frozenset(BlockEntry(p, True) for n in names for p in _parents(normalize_domain(n)))
    return {source.id: entries for source in config.sources}


REQUIRED = [(s["name"], d) for s in CATALOG["services"] for d in s["required"]]


def test_catalog_covers_every_service_the_owner_listed() -> None:
    names = {s["name"] for s in CATALOG["services"]}
    for expected in (
        "YouTube",
        "Twitch",
        "Netflix",
        "Prime Video",
        "Disney+",
        "DAZN",
        "Google",
        "Microsoft",
        "Apple",
        "Amazon",
        "Steam",
        "Xbox",
        "PlayStation",
        "Instagram",
        "Facebook",
        "TikTok",
        "X",
        "Reddit",
        "Telegram",
        "WhatsApp",
        "Discord",
        "Snapchat",
        "Italian public services",
        "Banks and payments",
        "Infrastructure",
    ):
        assert expected in names


def test_groups_are_exactly_the_six_approved(config: FilteringConfig) -> None:
    assert [g.id for g in config.groups] == [
        "DEFAULT",
        "PC",
        "GAMING",
        "MOBILE",
        "SMART-TV",
        "XBOX",
    ]


def test_group_policy_mapping(config: FilteringConfig) -> None:
    engine = PolicyEngine(config, {}, now=NOW)
    pro, tif, light, normal = "hagezi-multi-pro", "hagezi-tif-mini", "hagezi-light", "hagezi-normal"
    assert {g: engine.sources_for(g) for g in GROUPS} == {
        "DEFAULT": (pro, tif),
        "PC": (pro, tif),
        "MOBILE": (pro, tif),
        "GAMING": (normal, tif),
        "SMART-TV": (light, tif),
        "XBOX": (light, tif),
    }


@pytest.mark.parametrize(("service", "domain"), REQUIRED)
def test_required_endpoint_allowed_for_every_group_under_hostile_lists(
    config: FilteringConfig, service: str, domain: str
) -> None:
    engine = PolicyEngine(config, _hostile(config), now=NOW)
    for group in GROUPS:
        decision = engine.decide(group, domain)
        assert not decision.blocked, f"{service}: {domain} blocked for {group}: {decision.detail}"
        assert decision.reason is Reason.PROTECTED


@pytest.mark.parametrize("domain", CATALOG["must_stay_blockable"])
def test_telemetry_and_tenants_are_not_protected(config: FilteringConfig, domain: str) -> None:
    engine = PolicyEngine(config, _hostile(config), now=NOW)
    for group in GROUPS:
        decision = engine.decide(group, domain)
        assert decision.blocked, f"{domain} is protected for {group}: {decision.detail}"


def test_googlevideo_and_twitch_video_are_protected_as_subtrees(config: FilteringConfig) -> None:
    subtree = {p.domain for p in config.protected_domains() if p.include_subdomains}
    assert {"googlevideo.com", "ytimg.com", "ttvnw.net", "jtvnw.net", "nflxvideo.net"} <= subtree


def test_multi_tenant_platforms_are_only_exact_apex_guards(config: FilteringConfig) -> None:
    for entry in config.protected_domains():
        for apex in MULTI_TENANT_APEXES:
            if entry.domain == apex or entry.domain.endswith("." + apex):
                assert not entry.include_subdomains, f"{entry.domain} must not protect tenants"


def test_every_protected_entry_documents_reason_and_source(config: FilteringConfig) -> None:
    entries = config.protected_domains()
    assert len(entries) >= 250
    assert all(len(e.reason) >= 10 and len(e.source) >= 10 for e in entries)
    assert len({(e.domain, e.include_subdomains) for e in entries}) == len(entries)


@pytest.mark.parametrize(
    ("entry", "protected"),
    [
        (BlockEntry("googlevideo.com", True), "googlevideo.com"),
        (BlockEntry("rr1---sn-x.googlevideo.com", True), "googlevideo.com"),
        (BlockEntry("xboxlive.com", True), "xboxlive.com"),
        (BlockEntry("auth.xboxlive.com", True), "device.auth.xboxlive.com"),
        (BlockEntry("poste.it", False), "poste.it"),
        (BlockEntry("gov.it", True), "gov.it"),
        (BlockEntry("cloudfront.net", True), "cloudfront.net"),
        (BlockEntry("ttvnw.net", True), "ttvnw.net"),
    ],
)
def test_tripwire_catches_dangerous_entries_against_real_protected_set(
    config: FilteringConfig, entry: BlockEntry, protected: str
) -> None:
    hits = find_tripwire_hits([entry], config.protected_domains())
    assert protected in {h.protected_domain for h in hits}


@pytest.mark.parametrize(
    "domain",
    [
        "beacons.xboxlive.com",
        "sonar-ams.xx.fbcdn.net",
        "evil-tenant.cloudfront.net",
        "metrics.indazn.com",
    ],
)
def test_tripwire_ignores_legitimate_blocks_inside_exact_entries(
    config: FilteringConfig, domain: str
) -> None:
    assert find_tripwire_hits([BlockEntry(domain, True)], config.protected_domains()) == []


def test_policy_levels_differ_per_group(config: FilteringConfig) -> None:
    lists = {
        "hagezi-multi-pro": frozenset(
            {BlockEntry("pro-only.example", True), BlockEntry("common-ad.example", True)}
        ),
        "hagezi-normal": frozenset(
            {BlockEntry("normal-only.example", True), BlockEntry("common-ad.example", True)}
        ),
        "hagezi-light": frozenset({BlockEntry("common-ad.example", True)}),
        "hagezi-tif-mini": frozenset({BlockEntry("phish.example", True)}),
    }
    engine = PolicyEngine(config, lists, now=NOW)
    blocked = {
        g: {
            d
            for d in (
                "pro-only.example",
                "normal-only.example",
                "common-ad.example",
                "phish.example",
            )
            if engine.decide(g, d).blocked
        }
        for g in GROUPS
    }
    everyone = {"common-ad.example", "phish.example"}
    assert (
        blocked["DEFAULT"] == blocked["PC"] == blocked["MOBILE"] == everyone | {"pro-only.example"}
    )
    assert blocked["GAMING"] == everyone | {"normal-only.example"}
    assert blocked["SMART-TV"] == blocked["XBOX"] == everyone
