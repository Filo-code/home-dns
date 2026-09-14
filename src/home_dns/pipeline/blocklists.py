"""Blocklist update pipeline (A2).

Owner-approved order, per source:

 1 download            2 HTTP/content        3 size               4 format + header/date
 5 parse               6 normalization       7 deduplication      8 protected-domain tripwire
 9 syntax validation  10 sanity             11 test deployment   12 health check
13 activation

Steps 1-7 run per download attempt (primary, then fallback). An attempt is accepted only
if every step passes and the list is fresh. If no attempt is accepted, the previously
active artifact is kept. Steps 8-13 run on the accepted attempt; any failure stops the
update and keeps the previous artifact. The protected-domain tripwire is a hard gate that
``accept_anomalies`` never bypasses.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Literal

from home_dns.core.blocklists import (
    ArtifactFormatError,
    BlockEntry,
    Delta,
    ParseResult,
    Verdict,
    compute_delta,
    evaluate_sanity,
    find_tripwire_hits,
    parse_artifact,
    parse_list,
    render_artifact,
)
from home_dns.core.filtering import BlocklistSource, ListFormat, ProtectedDomain
from home_dns.core.models import HealthStatus
from home_dns.pipeline.fetch import Fetcher, FetchError, FetchResponse
from home_dns.providers.base import DnsProvider, ProviderError
from home_dns.storage.artifacts import ArtifactStore, ArtifactStoreError, sha256_text


class Stage(StrEnum):
    DOWNLOAD = "download"
    HTTP_CONTENT = "http_content"
    SIZE = "size"
    FORMAT = "format"
    PARSE = "parse"
    NORMALIZE = "normalize"
    DEDUPLICATE = "deduplicate"
    TRIPWIRE = "protected_domain_tripwire"
    SYNTAX = "syntax_validation"
    SANITY = "sanity"
    TEST_DEPLOYMENT = "test_deployment"
    HEALTH_CHECK = "health_check"
    ACTIVATION = "activation"


class StageStatus(StrEnum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"
    SKIPPED = "skipped"


class Outcome(StrEnum):
    ACTIVATED = "activated"
    WOULD_ACTIVATE = "would_activate"  # dry-run: everything passed
    UNCHANGED = "unchanged"  # identical to the current artifact
    HELD_FOR_REVIEW = "held_for_review"  # sanity anomaly; previous artifact kept
    KEPT_PREVIOUS = "kept_previous"  # no acceptable download (failed, stale or suspicious)
    BLOCKED_BY_TRIPWIRE = "blocked_by_tripwire"
    FAILED = "failed"  # validation, test deployment, health check or activation failed


AlertSeverity = Literal["critical", "warning", "info"]


@dataclass(frozen=True)
class StageResult:
    stage: Stage
    status: StageStatus
    detail: str


@dataclass(frozen=True)
class Alert:
    severity: AlertSeverity
    event: str  # names from config/telegram/alerts.yaml
    message: str


@dataclass(frozen=True)
class PipelineOptions:
    now: datetime
    dry_run: bool = True
    accept_anomalies: bool = False
    min_bytes: int = 1024
    max_bytes: int = 50 * 1024 * 1024
    max_invalid_ratio: float = 0.01  # owner-approved hard guard (observed 0.00 %)
    max_clock_skew: timedelta = timedelta(minutes=15)
    health_sample_size: int = 25


@dataclass
class AttemptReport:
    role: Literal["primary", "fallback"]
    url: str
    stages: list[StageResult] = field(default_factory=list)
    accepted: bool = False
    reason: str = ""
    stale: bool = False


@dataclass
class SourceReport:
    source_id: str
    outcome: Outcome
    attempts: list[AttemptReport]
    stages: list[StageResult]
    alerts: list[Alert]
    stats: dict[str, Any] = field(default_factory=dict)
    artifact_sha256: str | None = None
    previous_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _Accepted:
    attempt: AttemptReport
    response: FetchResponse
    parsed: ParseResult


def _stage(
    report: AttemptReport | list[StageResult], stage: Stage, status: StageStatus, detail: str
) -> bool:
    target = report.stages if isinstance(report, AttemptReport) else report
    target.append(StageResult(stage, status, detail))
    return status is not StageStatus.FAILED


def _looks_like_html(body: bytes) -> bool:
    head = body[:2048].lstrip().lower()
    return head.startswith((b"<!doctype", b"<html")) or b"<html" in head


def _attempt(
    source: BlocklistSource,
    role: Literal["primary", "fallback"],
    url: str,
    fetcher: Fetcher,
    options: PipelineOptions,
) -> tuple[AttemptReport, _Accepted | None]:
    report = AttemptReport(role=role, url=url)

    def reject(stage: Stage, reason: str, *, stale: bool = False) -> tuple[AttemptReport, None]:
        _stage(report, stage, StageStatus.FAILED, reason)
        report.reason, report.stale = reason, stale
        return report, None

    # 1 download
    try:
        response = fetcher.fetch(url, max_bytes=options.max_bytes)
    except FetchError as exc:
        return reject(Stage.DOWNLOAD, str(exc))
    _stage(report, Stage.DOWNLOAD, StageStatus.PASSED, f"{len(response.body)} bytes")

    # 2 HTTP/content correctness
    content_type = (response.content_type or "").split(";")[0].strip().lower()
    if response.status != 200:
        return reject(Stage.HTTP_CONTENT, f"HTTP status {response.status}")
    if content_type != "text/plain":
        return reject(Stage.HTTP_CONTENT, f"unexpected content type {response.content_type!r}")
    if _looks_like_html(response.body):
        return reject(Stage.HTTP_CONTENT, "body looks like HTML")
    try:
        text = response.body.decode("utf-8")
    except UnicodeDecodeError as exc:
        return reject(Stage.HTTP_CONTENT, f"body is not valid UTF-8: {exc}")
    _stage(report, Stage.HTTP_CONTENT, StageStatus.PASSED, f"200 {content_type}, UTF-8")

    # 3 size
    size = len(response.body)
    if size < options.min_bytes or size > options.max_bytes:
        return reject(
            Stage.SIZE, f"{size} bytes outside [{options.min_bytes}, {options.max_bytes}]"
        )
    _stage(report, Stage.SIZE, StageStatus.PASSED, f"{size} bytes")

    # 4 format + header/date freshness
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if source.format is ListFormat.ADBLOCK and not first.startswith(("[Adblock", "!")):
        return reject(Stage.FORMAT, f"expected an Adblock header, found {first[:60]!r}")
    parsed = parse_list(text, source.format)  # parsing is pure; staged reporting follows
    header = parsed.header
    if source.max_age_hours is not None:
        if header.last_modified is None:
            return reject(Stage.FORMAT, "header has no parseable 'Last modified' date")
        age = options.now - header.last_modified
        if age < -options.max_clock_skew:
            return reject(
                Stage.FORMAT, f"'Last modified' {header.last_modified.isoformat()} is in the future"
            )
        if age > timedelta(hours=source.max_age_hours):
            hours = age.total_seconds() / 3600
            return reject(
                Stage.FORMAT,
                f"stale: last modified {hours:.1f}h ago (limit {source.max_age_hours}h)",
                stale=True,
            )
    _stage(
        report,
        Stage.FORMAT,
        StageStatus.PASSED,
        f"version {header.version}, last modified {header.last_modified}",
    )

    # 5 parse
    if parsed.rule_lines == 0:
        return reject(Stage.PARSE, "no rule lines")
    _stage(
        report,
        Stage.PARSE,
        StageStatus.PASSED,
        f"{parsed.total_lines} lines, {parsed.rule_lines} rules, {parsed.comment_lines} comments",
    )

    # 6 normalization
    if parsed.invalid_ratio > options.max_invalid_ratio:
        return reject(
            Stage.NORMALIZE,
            f"{parsed.invalid_count} invalid rules "
            f"({parsed.invalid_ratio:.2%} > {options.max_invalid_ratio:.2%})",
        )
    _stage(
        report,
        Stage.NORMALIZE,
        StageStatus.WARNING if parsed.invalid_count else StageStatus.PASSED,
        f"{parsed.invalid_count} invalid rules dropped",
    )

    # 7 deduplication (+ declared entry count as a truncation check)
    declared = header.declared_entries
    if declared is not None and declared != parsed.rule_lines:
        return reject(
            Stage.DEDUPLICATE, f"header declares {declared} entries, found {parsed.rule_lines}"
        )
    _stage(
        report,
        Stage.DEDUPLICATE,
        StageStatus.PASSED,
        f"{len(parsed.entries)} unique entries, {parsed.duplicate_count} duplicates removed",
    )

    report.accepted = True
    return report, _Accepted(report, response, parsed)


def _health_sample(entries: frozenset[BlockEntry], size: int) -> list[BlockEntry]:
    ordered = sorted(entries)
    if len(ordered) <= size:
        return ordered
    step = len(ordered) / size
    return [ordered[int(i * step)] for i in range(size)]


def update_source(
    source: BlocklistSource,
    *,
    protected: Sequence[ProtectedDomain],
    fetcher: Fetcher,
    store: ArtifactStore,
    test_provider_factory: Callable[[], DnsProvider],
    options: PipelineOptions,
) -> SourceReport:
    alerts: list[Alert] = []
    stages: list[StageResult] = []
    previous_sha = store.state(source.id).current

    def finish(outcome: Outcome, **extra: Any) -> SourceReport:
        return SourceReport(
            source.id, outcome, attempts, stages, alerts, previous_sha256=previous_sha, **extra
        )

    attempts: list[AttemptReport] = []
    accepted: _Accepted | None = None
    urls = [("primary", str(source.urls.primary))]
    if source.urls.fallback is not None:
        urls.append(("fallback", str(source.urls.fallback)))
    for role, url in urls:
        attempt, accepted = _attempt(source, role, url, fetcher, options)  # type: ignore[arg-type]
        attempts.append(attempt)
        if accepted is not None:
            break

    if accepted is None:
        reasons = "; ".join(f"{a.role}: {a.reason}" for a in attempts)
        suspicious = any(
            a.stale or (bool(a.stages) and a.stages[-1].stage is not Stage.DOWNLOAD)
            for a in attempts
        )
        event = "suspicious_blocklist" if suspicious else "blocklist_update_failure"
        kept = (
            f"keeping active artifact {previous_sha[:12]}"
            if previous_sha
            else "no active artifact exists"
        )
        alerts.append(
            Alert("warning", event, f"{source.id}: no acceptable download ({reasons}); {kept}")
        )
        return finish(Outcome.KEPT_PREVIOUS)

    parsed = accepted.parsed
    entries = parsed.entries
    stats: dict[str, Any] = {
        "selected": accepted.attempt.role,
        "url": accepted.attempt.url,
        "bytes": len(accepted.response.body),
        "lines": parsed.total_lines,
        "rules": parsed.rule_lines,
        "valid_entries": len(entries),
        "invalid_rules": parsed.invalid_count,
        "duplicates": parsed.duplicate_count,
        "declared_entries": parsed.header.declared_entries,
        "version": parsed.header.version,
        "last_modified": parsed.header.last_modified.isoformat()
        if parsed.header.last_modified
        else None,
    }

    # 8 protected-domain tripwire (hard gate)
    if not protected:
        detail = "no protected domains configured; tripwire cannot verify this list"
        if not options.dry_run:
            _stage(stages, Stage.TRIPWIRE, StageStatus.FAILED, detail + " (activation refused)")
            alerts.append(
                Alert("critical", "protected_domain_tripwire_failure", f"{source.id}: {detail}")
            )
            return finish(Outcome.BLOCKED_BY_TRIPWIRE, stats=stats)
        _stage(stages, Stage.TRIPWIRE, StageStatus.WARNING, detail)
        alerts.append(Alert("warning", "protected_domain_warning", f"{source.id}: {detail}"))
    else:
        hits = find_tripwire_hits(entries, protected)
        if hits:
            sample = ", ".join(f"{h.entry.domain} -> {h.protected_domain}" for h in hits[:10])
            _stage(stages, Stage.TRIPWIRE, StageStatus.FAILED, f"{len(hits)} hit(s): {sample}")
            alerts.append(
                Alert(
                    "critical",
                    "protected_domain_tripwire_failure",
                    f"{source.id}: deployment aborted, {len(hits)} protected hit(s): {sample}",
                )
            )
            stats["tripwire_hits"] = len(hits)
            return finish(Outcome.BLOCKED_BY_TRIPWIRE, stats=stats)
        _stage(
            stages,
            Stage.TRIPWIRE,
            StageStatus.PASSED,
            f"0 hits against {len(protected)} protected domains",
        )

    # 9 syntax validation of the rendered artifact
    rendered = render_artifact(source.id, entries)
    try:
        if parse_artifact(rendered) != entries:
            raise ArtifactFormatError("round trip changed the entry set")
    except ArtifactFormatError as exc:
        _stage(stages, Stage.SYNTAX, StageStatus.FAILED, str(exc))
        alerts.append(
            Alert("critical", "failed_deployment", f"{source.id}: artifact invalid: {exc}")
        )
        return finish(Outcome.FAILED, stats=stats)
    sha = sha256_text(rendered)
    _stage(
        stages,
        Stage.SYNTAX,
        StageStatus.PASSED,
        f"artifact {sha[:12]} round-trips ({len(rendered)} bytes)",
    )

    if sha == previous_sha:
        for stage in (Stage.SANITY, Stage.TEST_DEPLOYMENT, Stage.HEALTH_CHECK, Stage.ACTIVATION):
            _stage(stages, stage, StageStatus.SKIPPED, "identical to active artifact")
        return finish(Outcome.UNCHANGED, stats=stats, artifact_sha256=sha)

    # 10 sanity
    delta: Delta | None = None
    if previous_sha is not None:
        try:
            delta = compute_delta(parse_artifact(store.read(source.id, previous_sha).text), entries)
        except (ArtifactStoreError, ArtifactFormatError) as exc:
            alerts.append(
                Alert(
                    "warning",
                    "suspicious_blocklist",
                    f"{source.id}: active artifact unreadable, delta not computed: {exc}",
                )
            )
    if delta is not None:
        stats.update(
            previous_entries=delta.previous_entries,
            added=delta.added,
            removed=delta.removed,
            added_ratio=round(delta.added_ratio, 6),
            removed_ratio=round(delta.removed_ratio, 6),
        )
    sanity = evaluate_sanity(parsed, delta, source.sanity)
    detail = "; ".join(sanity.findings) or "within approved limits"
    if sanity.verdict is Verdict.FAIL:
        _stage(stages, Stage.SANITY, StageStatus.FAILED, detail)
        alerts.append(
            Alert("warning", "suspicious_blocklist", f"{source.id}: sanity failure: {detail}")
        )
        return finish(Outcome.FAILED, stats=stats, artifact_sha256=sha)
    if sanity.verdict is Verdict.ANOMALY and not options.accept_anomalies:
        _stage(stages, Stage.SANITY, StageStatus.FAILED, f"anomaly held for review: {detail}")
        alerts.append(
            Alert(
                "warning",
                "suspicious_blocklist",
                f"{source.id}: anomaly held for review, previous artifact kept: {detail}",
            )
        )
        return finish(Outcome.HELD_FOR_REVIEW, stats=stats, artifact_sha256=sha)
    status = (
        StageStatus.WARNING
        if sanity.verdict is Verdict.ANOMALY or source.sanity is None
        else StageStatus.PASSED
    )
    _stage(
        stages,
        Stage.SANITY,
        status,
        ("anomaly accepted by operator: " if sanity.verdict is Verdict.ANOMALY else "") + detail,
    )

    # 11 test deployment (isolated test provider, never production)
    provider = test_provider_factory()
    try:
        deployment = provider.deploy_blocklist(source.id, entries, dry_run=False)
    except ProviderError as exc:
        _stage(stages, Stage.TEST_DEPLOYMENT, StageStatus.FAILED, str(exc))
        alerts.append(
            Alert("critical", "failed_deployment", f"{source.id}: test deployment failed: {exc}")
        )
        return finish(Outcome.FAILED, stats=stats, artifact_sha256=sha)
    if not deployment.applied or deployment.entries != len(entries):
        _stage(
            stages,
            Stage.TEST_DEPLOYMENT,
            StageStatus.FAILED,
            f"provider applied={deployment.applied} entries={deployment.entries}",
        )
        alerts.append(
            Alert("critical", "failed_deployment", f"{source.id}: test deployment incomplete")
        )
        return finish(Outcome.FAILED, stats=stats, artifact_sha256=sha)
    _stage(
        stages,
        Stage.TEST_DEPLOYMENT,
        StageStatus.PASSED,
        f"{deployment.entries} entries on {provider.name}",
    )

    # 12 health check
    problems: list[str] = []
    try:
        if provider.health().status is not HealthStatus.OK:
            problems.append("test provider not healthy")
        for entry in _health_sample(entries, options.health_sample_size):
            if source.id not in provider.lookup_domain(entry.domain).matched_sources:
                problems.append(f"{entry.domain} not blocked")
        for item in protected:
            if provider.lookup_domain(item.domain).blocked:
                problems.append(f"protected {item.domain} is blocked")
    except ProviderError as exc:
        problems.append(str(exc))
    if problems:
        _stage(stages, Stage.HEALTH_CHECK, StageStatus.FAILED, "; ".join(problems[:10]))
        alerts.append(
            Alert(
                "critical",
                "health_check_failure",
                f"{source.id}: post-deployment health check failed: {problems[0]}",
            )
        )
        return finish(Outcome.FAILED, stats=stats, artifact_sha256=sha)
    _stage(
        stages,
        Stage.HEALTH_CHECK,
        StageStatus.PASSED,
        f"{min(len(entries), options.health_sample_size)} sampled entries blocked, "
        f"{len(protected)} protected domains resolvable",
    )

    # 13 activation
    metadata = {
        "source_id": source.id,
        "sha256": sha,
        "activated_at": options.now.isoformat(),
        **stats,
    }
    try:
        change = store.activate(source.id, rendered, metadata, dry_run=options.dry_run)
    except (ArtifactStoreError, OSError) as exc:
        _stage(stages, Stage.ACTIVATION, StageStatus.FAILED, str(exc))
        alerts.append(
            Alert("critical", "failed_deployment", f"{source.id}: activation failed: {exc}")
        )
        return finish(Outcome.FAILED, stats=stats, artifact_sha256=sha)
    if options.dry_run:
        _stage(stages, Stage.ACTIVATION, StageStatus.SKIPPED, f"dry-run: would activate {sha[:12]}")
        return finish(Outcome.WOULD_ACTIVATE, stats=stats, artifact_sha256=sha)
    _stage(
        stages,
        Stage.ACTIVATION,
        StageStatus.PASSED,
        f"current {sha[:12]}, previous {(change.after.previous or '-')[:12]}, "
        f"backup {(change.after.backup or '-')[:12]}, pruned {len(change.pruned)} file(s)",
    )
    alerts.append(
        Alert(
            "info",
            "blocklist_updated",
            f"{source.id}: activated {sha[:12]} ({len(entries)} entries)",
        )
    )
    return finish(Outcome.ACTIVATED, stats=stats, artifact_sha256=sha)


def run_update(
    sources: Sequence[BlocklistSource],
    *,
    protected: Sequence[ProtectedDomain],
    fetcher: Fetcher,
    store: ArtifactStore,
    test_provider_factory: Callable[[], DnsProvider],
    options: PipelineOptions,
) -> list[SourceReport]:
    return [
        update_source(
            source,
            protected=protected,
            fetcher=fetcher,
            store=store,
            test_provider_factory=test_provider_factory,
            options=options,
        )
        for source in sources
    ]
