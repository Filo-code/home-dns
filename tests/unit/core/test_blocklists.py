from datetime import UTC, datetime, timedelta

import pytest

from home_dns.core.blocklists import (
    ARTIFACT_MAGIC,
    ArtifactFormatError,
    BlockEntry,
    Delta,
    InvalidReason,
    Verdict,
    compute_delta,
    evaluate_sanity,
    find_tripwire_hits,
    parse_artifact,
    parse_header,
    parse_list,
    render_artifact,
)
from home_dns.core.filtering import ListFormat, ProtectedDomain, SanityLimits

HAGEZI_HEADER = """\
[Adblock Plus]
! Title: HaGeZi's Multi PRO - extended protection (recommended)
! Expires: 8 hours
! Last modified: 13 Sep 2026 08:15 UTC
! Version: 2026.0913.0815.00
! Syntax: AdBlock
! Number of entries: 222,607
!
"""


def test_parse_hagezi_header() -> None:
    header = parse_header(HAGEZI_HEADER.splitlines())
    assert header.title and header.title.startswith("HaGeZi")
    assert header.version == "2026.0913.0815.00"
    assert header.last_modified == datetime(2026, 9, 13, 8, 15, tzinfo=UTC)
    assert header.declared_entries == 222607
    assert header.expires == timedelta(hours=8)
    assert header.syntax == "AdBlock"


def test_header_variants_and_missing_fields() -> None:
    header = parse_header(
        ["# Expires: 2 days", "# Last modified: yesterday", "# Number of entries: n/a"]
    )
    assert header.expires == timedelta(days=2)
    assert header.last_modified is None
    assert header.declared_entries is None
    assert parse_header(["! Last modified: 2026-09-13T08:15:00"]).last_modified == datetime(
        2026, 9, 13, 8, 15, tzinfo=UTC
    )
    assert parse_header(["||a.example^"] * 60 + ["! Version: late"]).version is None


def test_parse_adblock_list() -> None:
    text = HAGEZI_HEADER + "\n".join(
        [
            "||Ads.Example.COM^",
            "||ads.example.com^",
            "||xn--bcher-kva.example^",
            "",
            "@@||allowed.example^",
            "||opt.example^$important",
            "/regex/",
            "plain.example",
            "||192.0.2.1^",
            "||-bad.example^",
        ]
    )
    parsed = parse_list(text, ListFormat.ADBLOCK)
    assert parsed.entries == {
        BlockEntry("ads.example.com", True),
        BlockEntry("xn--bcher-kva.example", True),
    }
    assert parsed.rule_lines == 9
    assert parsed.duplicate_count == 1
    assert parsed.invalid_count == 6
    assert parsed.valid_rules == 3
    reasons = {s.text: s.reason for s in parsed.invalid_samples}
    assert reasons["@@||allowed.example^"] is InvalidReason.UNSUPPORTED_SYNTAX
    assert reasons["||192.0.2.1^"] is InvalidReason.INVALID_DOMAIN
    assert parsed.comment_lines == 8 and parsed.blank_lines == 1
    assert parsed.invalid_ratio == pytest.approx(6 / 9)


def test_parse_hosts_list() -> None:
    text = "\n".join(
        [
            "# hosts",
            "0.0.0.0 localhost",
            "0.0.0.0 ads.example trackers.example  # inline comment",
            "127.0.0.1 metrics.example",
            "192.0.2.10 not-a-sink.example",
            "0.0.0.0",
        ]
    )
    parsed = parse_list(text, ListFormat.HOSTS)
    assert parsed.entries == {
        BlockEntry("ads.example", False),
        BlockEntry("trackers.example", False),
        BlockEntry("metrics.example", False),
    }
    assert parsed.invalid_count == 2


def test_parse_domains_list() -> None:
    parsed = parse_list(
        "# c\nads.example\nads.example # dup\ntwo words.example\n", ListFormat.DOMAINS
    )
    assert parsed.entries == {BlockEntry("ads.example", False)}
    assert parsed.duplicate_count == 1
    assert parsed.invalid_count == 1


def test_invalid_samples_are_capped() -> None:
    parsed = parse_list("\n".join(["bad rule"] * 100), ListFormat.ADBLOCK)
    assert parsed.invalid_count == 100
    assert len(parsed.invalid_samples) == 20


PROTECTED = [
    ProtectedDomain(
        domain="video.example", include_subdomains=True, reason="video CDN", source="t"
    ),
    ProtectedDomain(
        domain="login.bank.example", include_subdomains=False, reason="login", source="t"
    ),
]


@pytest.mark.parametrize(
    ("entry", "protected", "relation"),
    [
        (BlockEntry("video.example", False), "video.example", "exact"),
        (BlockEntry("edge.video.example", True), "video.example", "entry-inside-protected"),
        (BlockEntry("bank.example", True), "login.bank.example", "entry-covers-protected"),
        (BlockEntry("login.bank.example", False), "login.bank.example", "exact"),
    ],
)
def test_tripwire_hits(entry: BlockEntry, protected: str, relation: str) -> None:
    hits = find_tripwire_hits([entry], PROTECTED)
    assert [(h.protected_domain, h.relation) for h in hits] == [(protected, relation)]


@pytest.mark.parametrize(
    "entry",
    [
        BlockEntry("notvideo.example", True),
        BlockEntry("bank.example", False),  # exact parent does not cover the child
        BlockEntry("x.login.bank.example", True),  # protected entry is exact-only
        BlockEntry("other.example", True),
    ],
)
def test_tripwire_no_false_positives(entry: BlockEntry) -> None:
    assert find_tripwire_hits([entry], PROTECTED) == []


def test_render_is_deterministic_and_round_trips() -> None:
    entries = frozenset({BlockEntry("b.example", True), BlockEntry("a.example", False)})
    text = render_artifact("list-a", entries)
    assert text == render_artifact("list-a", set(reversed(sorted(entries))))
    assert text.splitlines()[:3] == [ARTIFACT_MAGIC, "! source: list-a", "! entries: 2"]
    assert text.splitlines()[3:] == ["a.example", "||b.example^"]
    assert parse_artifact(text) == entries


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "missing artifact header"),
        ("! something else\n", "missing artifact header"),
        (f"{ARTIFACT_MAGIC}\n! entries: 1\nUPPER.example\n", "not normalized"),
        (f"{ARTIFACT_MAGIC}\n! entries: 1\n||*.example^\n", "line 3"),
        (f"{ARTIFACT_MAGIC}\n! entries: 2\na.example\n", "declared entries 2 != parsed 1"),
        (f"{ARTIFACT_MAGIC}\na.example\n", "declared entries None"),
    ],
)
def test_parse_artifact_rejects_invalid_text(text: str, message: str) -> None:
    with pytest.raises(ArtifactFormatError, match=message):
        parse_artifact(text)


def _parsed(count: int):  # type: ignore[no-untyped-def]
    return parse_list("\n".join(f"||d{i}.example^" for i in range(count)), ListFormat.ADBLOCK)


def test_compute_delta() -> None:
    previous = frozenset({BlockEntry("a.example", True), BlockEntry("b.example", True)})
    current = frozenset(
        {
            BlockEntry("b.example", True),
            BlockEntry("c.example", True),
            BlockEntry("d.example", True),
        }
    )
    delta = compute_delta(previous, current)
    assert (delta.previous_entries, delta.added, delta.removed) == (2, 2, 1)
    assert delta.added_ratio == 1.0 and delta.removed_ratio == 0.5
    assert Delta(0, 5, 0).added_ratio == 0.0


def test_sanity_without_limits_passes_with_note() -> None:
    result = evaluate_sanity(_parsed(10), None, None)
    assert result.verdict is Verdict.PASS
    assert "no approved sanity limits" in result.findings[0]


def test_sanity_empty_list_fails_even_without_limits() -> None:
    assert evaluate_sanity(_parsed(0), None, None).verdict is Verdict.FAIL


@pytest.mark.parametrize(
    ("limits", "delta", "fragment"),
    [
        (SanityLimits(min_entries=20), None, "below approved minimum"),
        (SanityLimits(max_entries=5), None, "above approved maximum"),
        (SanityLimits(max_added_ratio=0.1), Delta(10, 2, 0), "added 20.00%"),
        (SanityLimits(max_removed_ratio=0.1), Delta(10, 0, 5), "removed 50.00%"),
    ],
)
def test_sanity_limits_produce_anomalies_not_failures(
    limits: SanityLimits, delta: Delta | None, fragment: str
) -> None:
    result = evaluate_sanity(_parsed(10), delta, limits)
    assert result.verdict is Verdict.ANOMALY
    assert any(fragment in f for f in result.findings)


def test_sanity_within_limits_and_first_run() -> None:
    limits = SanityLimits(min_entries=5, max_entries=50, max_added_ratio=0.5, max_removed_ratio=0.5)
    assert evaluate_sanity(_parsed(10), Delta(10, 1, 1), limits).verdict is Verdict.PASS
    assert evaluate_sanity(_parsed(10), None, limits).verdict is Verdict.PASS
    assert evaluate_sanity(_parsed(10), Delta(0, 10, 0), limits).verdict is Verdict.PASS
