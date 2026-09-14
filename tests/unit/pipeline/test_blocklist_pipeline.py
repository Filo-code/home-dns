import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from home_dns.core.blocklists import BlockEntry
from home_dns.core.filtering import BlocklistSource, ProtectedDomain
from home_dns.core.models import BlocklistDeployment, DomainLookup, HealthStatus
from home_dns.pipeline.blocklists import (
    Outcome,
    PipelineOptions,
    Stage,
    StageStatus,
    run_update,
    update_source,
)
from home_dns.pipeline.fetch import FetchError, FetchResponse
from home_dns.providers.base import DnsProvider, ProviderUnavailableError
from home_dns.providers.mock import MockDnsProvider
from home_dns.storage.artifacts import ArtifactStore
from tests.blocklist_fixtures import ScriptedFetcher, adblock_list, domains, ok

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
PRIMARY = "https://cdn.example/list.txt"
FALLBACK = "https://mirror.example/list.txt"
FRESH = NOW - timedelta(hours=4)
STALE = NOW - timedelta(hours=72)
PROTECTED = [ProtectedDomain(domain="video.example", reason="video CDN", source="test")]


def _source(**overrides: Any) -> BlocklistSource:
    values: dict[str, Any] = {
        "id": "list-a",
        "name": "List A",
        "homepage": "https://lists.example",
        "license": "GPL-3.0",
        "format": "adblock",
        "categories": ["advertising"],
        "urls": {"primary": PRIMARY, "fallback": FALLBACK},
        "update_interval_hours": 24,
        "max_age_hours": 48,
    }
    values.update(overrides)
    return BlocklistSource(**values)


def _run(
    fetcher: ScriptedFetcher,
    store: ArtifactStore,
    *,
    source: BlocklistSource | None = None,
    protected: list[ProtectedDomain] | None = None,
    provider_factory: Any = MockDnsProvider,
    **options: Any,
):  # type: ignore[no-untyped-def]
    return update_source(
        source or _source(),
        protected=PROTECTED if protected is None else protected,
        fetcher=fetcher,
        store=store,
        test_provider_factory=provider_factory,
        options=PipelineOptions(now=NOW, **options),
    )


def _fresh(count: int = 50, prefix: str = "ads", **kwargs: Any) -> str:
    return adblock_list(
        domains(count, prefix), last_modified=kwargs.pop("last_modified", FRESH), **kwargs
    )


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(tmp_path / "store")


def _activate_previous(store: ArtifactStore, count: int = 50, prefix: str = "ads") -> str:
    report = _run(
        ScriptedFetcher({PRIMARY: ok(PRIMARY, _fresh(count, prefix))}), store, dry_run=False
    )
    assert report.outcome is Outcome.ACTIVATED
    assert report.artifact_sha256
    return report.artifact_sha256


# ------------------------------------------------------------------------------ happy path


def test_dry_run_runs_all_thirteen_steps_and_writes_nothing(
    store: ArtifactStore, tmp_path: Path
) -> None:
    fetcher = ScriptedFetcher({PRIMARY: ok(PRIMARY, _fresh())})
    report = _run(fetcher, store)
    assert report.outcome is Outcome.WOULD_ACTIVATE
    assert fetcher.calls == [PRIMARY]
    steps = [s.stage for s in report.attempts[0].stages] + [s.stage for s in report.stages]
    assert steps == list(Stage)
    assert report.stages[-1].status is StageStatus.SKIPPED
    assert not (tmp_path / "store").exists()
    json.dumps(report.to_dict(), default=str)


def test_apply_activates_and_rerun_is_unchanged(store: ArtifactStore) -> None:
    sha = _activate_previous(store)
    assert store.state("list-a").current == sha
    report = _run(ScriptedFetcher({PRIMARY: ok(PRIMARY, _fresh())}), store, dry_run=False)
    assert report.outcome is Outcome.UNCHANGED
    assert all(s.status is StageStatus.SKIPPED for s in report.stages[-4:])


def test_activation_emits_info_alert_and_records_stats(store: ArtifactStore) -> None:
    report = _run(ScriptedFetcher({PRIMARY: ok(PRIMARY, _fresh(30))}), store, dry_run=False)
    assert [(a.severity, a.event) for a in report.alerts] == [("info", "blocklist_updated")]
    assert report.stats["valid_entries"] == 30 and report.stats["selected"] == "primary"
    stored = store.current("list-a")
    assert stored is not None and stored.metadata["sha256"] == report.artifact_sha256


def test_second_activation_records_delta_and_rollback_restores(store: ArtifactStore) -> None:
    first = _activate_previous(store, 50)
    report = _run(ScriptedFetcher({PRIMARY: ok(PRIMARY, _fresh(60))}), store, dry_run=False)
    assert report.outcome is Outcome.ACTIVATED
    assert (report.stats["added"], report.stats["removed"]) == (10, 0)
    store.rollback("list-a", dry_run=False)
    assert store.state("list-a").current == first


# ----------------------------------------------------------------------- source selection


def test_stale_primary_uses_fresh_fallback(store: ArtifactStore) -> None:
    fetcher = ScriptedFetcher(
        {
            PRIMARY: ok(PRIMARY, _fresh(last_modified=STALE)),
            FALLBACK: ok(FALLBACK, _fresh()),
        }
    )
    report = _run(fetcher, store, dry_run=False)
    assert report.outcome is Outcome.ACTIVATED
    assert report.stats["selected"] == "fallback"
    assert report.attempts[0].stale and "stale" in report.attempts[0].reason


def test_both_stale_keeps_previous_and_warns(store: ArtifactStore) -> None:
    previous = _activate_previous(store)
    fetcher = ScriptedFetcher(
        {
            PRIMARY: ok(PRIMARY, _fresh(70, last_modified=STALE)),
            FALLBACK: ok(FALLBACK, _fresh(70, last_modified=STALE)),
        }
    )
    report = _run(fetcher, store, dry_run=False)
    assert report.outcome is Outcome.KEPT_PREVIOUS
    assert store.state("list-a").current == previous
    assert [(a.severity, a.event) for a in report.alerts] == [("warning", "suspicious_blocklist")]
    assert "keeping active artifact" in report.alerts[0].message


def test_stale_primary_and_failed_fallback_does_not_use_stale_list(store: ArtifactStore) -> None:
    previous = _activate_previous(store)
    fetcher = ScriptedFetcher(
        {
            PRIMARY: ok(PRIMARY, _fresh(70, last_modified=STALE)),
            FALLBACK: FetchError("connection refused"),
        }
    )
    report = _run(fetcher, store, dry_run=False)
    assert report.outcome is Outcome.KEPT_PREVIOUS
    assert store.state("list-a").current == previous


def test_both_downloads_failing_is_an_update_failure(store: ArtifactStore) -> None:
    report = _run(ScriptedFetcher({}), store, dry_run=False)
    assert report.outcome is Outcome.KEPT_PREVIOUS
    assert report.alerts[0].event == "blocklist_update_failure"
    assert "no active artifact exists" in report.alerts[0].message


def test_no_fallback_configured(store: ArtifactStore) -> None:
    source = _source(urls={"primary": PRIMARY})
    report = _run(ScriptedFetcher({PRIMARY: FetchError("boom")}), store, source=source)
    assert report.outcome is Outcome.KEPT_PREVIOUS
    assert len(report.attempts) == 1


def _response(**overrides: Any) -> FetchResponse:
    values: dict[str, Any] = {
        "url": PRIMARY,
        "status": 200,
        "content_type": "text/plain",
        "body": _fresh().encode(),
    }
    values.update(overrides)
    return FetchResponse(**values)


@pytest.mark.parametrize(
    ("primary", "stage", "fragment"),
    [
        (_response(status=500), Stage.HTTP_CONTENT, "HTTP status 500"),
        (_response(status=302), Stage.HTTP_CONTENT, "HTTP status 302"),
        (_response(content_type="text/html"), Stage.HTTP_CONTENT, "content type"),
        (_response(content_type=None), Stage.HTTP_CONTENT, "content type"),
        (
            _response(body=b"<!DOCTYPE html><html><body>captive portal</body></html>" * 40),
            Stage.HTTP_CONTENT,
            "HTML",
        ),
        (_response(body=b"\xff\xfe" + b"||a.example^\n" * 200), Stage.HTTP_CONTENT, "UTF-8"),
        (_response(body=b"||a.example^\n"), Stage.SIZE, "outside"),
        (_response(body=("\n".join(domains(200)) + "\n").encode()), Stage.FORMAT, "Adblock header"),
        (_response(body=_fresh(last_modified=None).encode()), Stage.FORMAT, "no parseable"),
        (
            _response(body=_fresh(last_modified=NOW + timedelta(hours=2)).encode()),
            Stage.FORMAT,
            "in the future",
        ),
        (
            _response(body=adblock_list([], last_modified=FRESH).encode()),
            Stage.PARSE,
            "no rule lines",
        ),
        (
            _response(body=_fresh(20, extra_lines=["bad"] * 5).encode()),
            Stage.NORMALIZE,
            "invalid rules",
        ),
        (_response(body=_fresh(50, declared=80).encode()), Stage.DEDUPLICATE, "declares 80"),
    ],
)
def test_suspicious_primary_falls_back(
    store: ArtifactStore, primary: FetchResponse, stage: Stage, fragment: str
) -> None:
    fetcher = ScriptedFetcher({PRIMARY: primary, FALLBACK: ok(FALLBACK, _fresh())})
    report = _run(fetcher, store)
    rejected = report.attempts[0]
    assert rejected.stages[-1].stage is stage
    assert fragment in rejected.reason
    assert report.outcome is Outcome.WOULD_ACTIVATE
    assert report.stats["selected"] == "fallback"


def test_oversize_body_is_rejected_at_download(store: ArtifactStore) -> None:
    fetcher = ScriptedFetcher({PRIMARY: ok(PRIMARY, _fresh(50))})
    report = _run(fetcher, store, max_bytes=2000)
    assert report.attempts[0].stages[-1].stage is Stage.DOWNLOAD
    assert report.outcome is Outcome.KEPT_PREVIOUS


def test_source_without_freshness_limit_accepts_undated_list(store: ArtifactStore) -> None:
    fetcher = ScriptedFetcher({PRIMARY: ok(PRIMARY, _fresh(last_modified=None))})
    assert (
        _run(fetcher, store, source=_source(max_age_hours=None)).outcome is Outcome.WOULD_ACTIVATE
    )


def test_few_invalid_rules_are_dropped_with_warning(store: ArtifactStore) -> None:
    fetcher = ScriptedFetcher({PRIMARY: ok(PRIMARY, _fresh(200, extra_lines=["@@||x.example^"]))})
    report = _run(fetcher, store)
    assert report.outcome is Outcome.WOULD_ACTIVATE
    normalize = next(s for s in report.attempts[0].stages if s.stage is Stage.NORMALIZE)
    assert normalize.status is StageStatus.WARNING


# ------------------------------------------------------------------------------ tripwire


def test_protected_domain_aborts_without_trying_fallback(store: ArtifactStore) -> None:
    previous = _activate_previous(store)
    bad = adblock_list([*domains(60), "edge.video.example"], last_modified=FRESH)
    fetcher = ScriptedFetcher({PRIMARY: ok(PRIMARY, bad), FALLBACK: ok(FALLBACK, _fresh())})
    report = _run(fetcher, store, dry_run=False, accept_anomalies=True)
    assert report.outcome is Outcome.BLOCKED_BY_TRIPWIRE
    assert fetcher.calls == [PRIMARY]
    assert store.state("list-a").current == previous
    assert report.alerts[0].severity == "critical"
    assert report.alerts[0].event == "protected_domain_tripwire_failure"
    assert "edge.video.example -> video.example" in report.alerts[0].message


def test_parent_rule_covering_protected_domain_is_caught(store: ArtifactStore) -> None:
    bad = adblock_list([*domains(60), "cdn.video.example"], last_modified=FRESH)
    protected = [
        ProtectedDomain(
            domain="api.cdn.video.example", include_subdomains=False, reason="api", source="t"
        )
    ]
    report = _run(ScriptedFetcher({PRIMARY: ok(PRIMARY, bad)}), store, protected=protected)
    assert report.outcome is Outcome.BLOCKED_BY_TRIPWIRE


def test_empty_protected_set_refuses_activation(store: ArtifactStore) -> None:
    fetcher = ScriptedFetcher({PRIMARY: ok(PRIMARY, _fresh())})
    report = _run(fetcher, store, protected=[], dry_run=False)
    assert report.outcome is Outcome.BLOCKED_BY_TRIPWIRE
    assert report.alerts[0].severity == "critical"
    assert store.state("list-a").current is None


def test_empty_protected_set_warns_in_dry_run(store: ArtifactStore) -> None:
    report = _run(ScriptedFetcher({PRIMARY: ok(PRIMARY, _fresh())}), store, protected=[])
    assert report.outcome is Outcome.WOULD_ACTIVATE
    assert report.stages[0].status is StageStatus.WARNING
    assert report.alerts[0].event == "protected_domain_warning"


# -------------------------------------------------------------------------------- sanity


def test_anomaly_is_held_for_review_and_previous_kept(store: ArtifactStore) -> None:
    source = _source(sanity={"max_removed_ratio": 0.1})
    previous = _run(
        ScriptedFetcher({PRIMARY: ok(PRIMARY, _fresh(100))}), store, source=source, dry_run=False
    ).artifact_sha256
    fetcher = ScriptedFetcher({PRIMARY: ok(PRIMARY, _fresh(50))})
    report = _run(fetcher, store, source=source, dry_run=False)
    assert report.outcome is Outcome.HELD_FOR_REVIEW
    assert store.state("list-a").current == previous
    assert report.alerts[0].event == "suspicious_blocklist"
    assert "removed 50.00%" in report.alerts[0].message


def test_operator_can_accept_a_reviewed_anomaly(store: ArtifactStore) -> None:
    source = _source(sanity={"max_removed_ratio": 0.1})
    _run(ScriptedFetcher({PRIMARY: ok(PRIMARY, _fresh(100))}), store, source=source, dry_run=False)
    report = _run(
        ScriptedFetcher({PRIMARY: ok(PRIMARY, _fresh(50))}),
        store,
        source=source,
        dry_run=False,
        accept_anomalies=True,
    )
    assert report.outcome is Outcome.ACTIVATED
    sanity = next(s for s in report.stages if s.stage is Stage.SANITY)
    assert sanity.status is StageStatus.WARNING and "accepted by operator" in sanity.detail


def test_within_approved_limits_passes(store: ArtifactStore) -> None:
    source = _source(sanity={"min_entries": 10, "max_entries": 1000})
    report = _run(ScriptedFetcher({PRIMARY: ok(PRIMARY, _fresh(50))}), store, source=source)
    assert next(s for s in report.stages if s.stage is Stage.SANITY).status is StageStatus.PASSED


def test_list_with_no_valid_entries_fails_sanity(store: ArtifactStore) -> None:
    text = adblock_list([], last_modified=FRESH, extra_lines=["@@||x.example^"] * 60)
    report = _run(ScriptedFetcher({PRIMARY: ok(PRIMARY, text)}), store, max_invalid_ratio=1.0)
    assert report.outcome is Outcome.FAILED
    assert next(s for s in report.stages if s.stage is Stage.SANITY).status is StageStatus.FAILED


def test_unreadable_previous_artifact_warns_but_continues(
    store: ArtifactStore, tmp_path: Path
) -> None:
    sha = _activate_previous(store)
    (tmp_path / "store" / "list-a" / "artifacts" / f"{sha}.txt").write_text("tampered\n")
    report = _run(ScriptedFetcher({PRIMARY: ok(PRIMARY, _fresh(60))}), store)
    assert report.outcome is Outcome.WOULD_ACTIVATE
    assert any("delta not computed" in a.message for a in report.alerts)


# ------------------------------------------------------------- test deployment and health


class _FailingDeploy(MockDnsProvider):
    def deploy_blocklist(
        self, source_id: str, entries: frozenset[BlockEntry], *, dry_run: bool = True
    ) -> BlocklistDeployment:
        raise ProviderUnavailableError("provider offline")


class _PartialDeploy(MockDnsProvider):
    def deploy_blocklist(
        self, source_id: str, entries: frozenset[BlockEntry], *, dry_run: bool = True
    ) -> BlocklistDeployment:
        return BlocklistDeployment(source_id=source_id, entries=1, dry_run=False, applied=True)


class _BlocksNothing(MockDnsProvider):
    def lookup_domain(self, domain: str) -> DomainLookup:
        return DomainLookup(domain=domain, blocked=False)


class _BlocksEverything(MockDnsProvider):
    def lookup_domain(self, domain: str) -> DomainLookup:
        return DomainLookup(domain=domain, blocked=True, matched_sources=("list-a",))


class _LookupErrors(MockDnsProvider):
    def lookup_domain(self, domain: str) -> DomainLookup:
        raise ProviderUnavailableError("lookup failed")


@pytest.mark.parametrize(
    ("factory", "stage", "event"),
    [
        (_FailingDeploy, Stage.TEST_DEPLOYMENT, "failed_deployment"),
        (_PartialDeploy, Stage.TEST_DEPLOYMENT, "failed_deployment"),
        (_BlocksNothing, Stage.HEALTH_CHECK, "health_check_failure"),
        (_BlocksEverything, Stage.HEALTH_CHECK, "health_check_failure"),
        (_LookupErrors, Stage.HEALTH_CHECK, "health_check_failure"),
        (
            lambda: MockDnsProvider(health_status=HealthStatus.DEGRADED),
            Stage.HEALTH_CHECK,
            "health_check_failure",
        ),
    ],
)
def test_test_deployment_and_health_failures_keep_previous(
    store: ArtifactStore, factory: Any, stage: Stage, event: str
) -> None:
    previous = _activate_previous(store)
    report = _run(
        ScriptedFetcher({PRIMARY: ok(PRIMARY, _fresh(60))}),
        store,
        provider_factory=factory,
        dry_run=False,
    )
    assert report.outcome is Outcome.FAILED
    assert report.stages[-1].stage is stage and report.stages[-1].status is StageStatus.FAILED
    assert report.alerts[-1].event == event
    assert store.state("list-a").current == previous


def test_activation_failure_is_reported(
    store: ArtifactStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: Any, **kwargs: Any) -> Any:
        raise OSError("disk full")

    monkeypatch.setattr(store, "activate", broken)
    report = _run(ScriptedFetcher({PRIMARY: ok(PRIMARY, _fresh())}), store, dry_run=False)
    assert report.outcome is Outcome.FAILED
    assert report.stages[-1].stage is Stage.ACTIVATION
    assert "disk full" in report.alerts[-1].message


def test_test_provider_is_a_fresh_instance_per_source(store: ArtifactStore) -> None:
    created: list[DnsProvider] = []

    def factory() -> DnsProvider:
        created.append(MockDnsProvider())
        return created[-1]

    sources = [_source(), _source(id="list-b", urls={"primary": "https://cdn.example/b.txt"})]
    fetcher = ScriptedFetcher(
        {
            PRIMARY: ok(PRIMARY, _fresh()),
            "https://cdn.example/b.txt": ok("https://cdn.example/b.txt", _fresh(prefix="trk")),
        }
    )
    reports = run_update(
        sources,
        protected=PROTECTED,
        fetcher=fetcher,
        store=store,
        test_provider_factory=factory,
        options=PipelineOptions(now=NOW),
    )
    assert [r.outcome for r in reports] == [Outcome.WOULD_ACTIVATE, Outcome.WOULD_ACTIVATE]
    assert len(created) == 2 and created[0] is not created[1]


# ------------------------------------------------------------------- syntax validation gate


@pytest.mark.parametrize(
    "broken_render",
    [
        lambda source_id, entries: "not an artifact\n",  # unparseable
        lambda source_id, entries: (  # parseable but loses entries
            "! home-dns blocklist artifact v1\n! entries: 1\n||only.example^\n"
        ),
    ],
)
def test_invalid_rendered_artifact_blocks_activation(
    store: ArtifactStore, monkeypatch: pytest.MonkeyPatch, broken_render: Any
) -> None:
    import home_dns.pipeline.blocklists as pipeline

    monkeypatch.setattr(pipeline, "render_artifact", broken_render)
    report = _run(ScriptedFetcher({PRIMARY: ok(PRIMARY, _fresh())}), store, dry_run=False)
    assert report.outcome is Outcome.FAILED
    assert report.stages[-1].stage is Stage.SYNTAX
    assert report.alerts[-1].severity == "critical"
    assert store.state("list-a").current is None


def test_health_sample_covers_small_lists_entirely(store: ArtifactStore) -> None:
    report = _run(
        ScriptedFetcher({PRIMARY: ok(PRIMARY, _fresh(60))}), store, health_sample_size=100
    )
    health = next(s for s in report.stages if s.stage is Stage.HEALTH_CHECK)
    assert health.status is StageStatus.PASSED and "60 sampled" in health.detail


# ------------------------------------------- --accept-anomalies never bypasses safety gates


def _gate_case(name: str) -> tuple[dict[str, Any], dict[str, Any], Outcome]:
    """(fetcher script, extra run kwargs, expected outcome) for each safety gate."""
    tripwire = adblock_list([*domains(60), "edge.video.example"], last_modified=FRESH)
    malformed = _fresh(60, extra_lines=["@@||x.example^"] * 5)  # 7.7 % invalid > 1 % guard
    truncated = _fresh(60, declared=90)
    stale = _fresh(60, last_modified=STALE)
    no_valid = adblock_list([], last_modified=FRESH, extra_lines=["@@||x.example^"] * 60)
    cases: dict[str, tuple[dict[str, Any], dict[str, Any], Outcome]] = {
        "protected_domain": ({PRIMARY: ok(PRIMARY, tripwire)}, {}, Outcome.BLOCKED_BY_TRIPWIRE),
        "no_protected_domains": (
            {PRIMARY: ok(PRIMARY, _fresh(60))},
            {"protected": []},
            Outcome.BLOCKED_BY_TRIPWIRE,
        ),
        "malformed_data": ({PRIMARY: ok(PRIMARY, malformed)}, {}, Outcome.KEPT_PREVIOUS),
        "truncated_data": ({PRIMARY: ok(PRIMARY, truncated)}, {}, Outcome.KEPT_PREVIOUS),
        "stale_data": ({PRIMARY: ok(PRIMARY, stale)}, {}, Outcome.KEPT_PREVIOUS),
        "html_data": (
            {PRIMARY: _response(body=b"<html>portal</html>" * 100)},
            {},
            Outcome.KEPT_PREVIOUS,
        ),
        "zero_valid_entries": (
            {PRIMARY: ok(PRIMARY, no_valid)},
            {"max_invalid_ratio": 1.0},
            Outcome.FAILED,
        ),
        "test_deployment": (
            {PRIMARY: ok(PRIMARY, _fresh(60))},
            {"provider_factory": _FailingDeploy},
            Outcome.FAILED,
        ),
        "health_check": (
            {PRIMARY: ok(PRIMARY, _fresh(60))},
            {"provider_factory": _BlocksNothing},
            Outcome.FAILED,
        ),
    }
    return cases[name]


@pytest.mark.parametrize(
    "gate",
    [
        "protected_domain",
        "no_protected_domains",
        "malformed_data",
        "truncated_data",
        "stale_data",
        "html_data",
        "zero_valid_entries",
        "test_deployment",
        "health_check",
    ],
)
def test_accept_anomalies_never_bypasses_safety_gates(store: ArtifactStore, gate: str) -> None:
    previous = _activate_previous(store, 50)
    script, extra, expected = _gate_case(gate)
    source = _source(urls={"primary": PRIMARY}, sanity={"max_added_ratio": 0.01})
    report = _run(
        ScriptedFetcher(script), store, source=source, dry_run=False, accept_anomalies=True, **extra
    )
    assert report.outcome is expected
    assert report.outcome is not Outcome.ACTIVATED
    assert store.state("list-a").current == previous


def test_invalid_rule_guard_is_one_percent(store: ArtifactStore) -> None:
    assert PipelineOptions(now=NOW).max_invalid_ratio == 0.01
    under = _fresh(200, extra_lines=["@@||x.example^"])  # 0.5 %
    over = _fresh(98, extra_lines=["@@||x.example^"] * 2)  # 2.0 %
    assert (
        _run(ScriptedFetcher({PRIMARY: ok(PRIMARY, under)}), store).outcome
        is Outcome.WOULD_ACTIVATE
    )
    report = _run(
        ScriptedFetcher({PRIMARY: ok(PRIMARY, over)}),
        store,
        source=_source(urls={"primary": PRIMARY}),
    )
    assert report.outcome is Outcome.KEPT_PREVIOUS
    assert "invalid rules" in report.attempts[0].reason


def test_pipeline_retains_three_versions(store: ArtifactStore, tmp_path: Path) -> None:
    for count in (50, 51, 52, 53):
        report = _run(ScriptedFetcher({PRIMARY: ok(PRIMARY, _fresh(count))}), store, dry_run=False)
        assert report.outcome is Outcome.ACTIVATED
    assert "pruned 2 file(s)" in report.stages[-1].detail
    artifacts = list((tmp_path / "store" / "list-a" / "artifacts").glob("*.txt"))
    assert len(artifacts) == 3
