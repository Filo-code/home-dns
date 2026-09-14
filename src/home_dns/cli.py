"""Command-line entry point: ``home-dns``.

Exit codes: 0 ready/ok, 1 not ready or refused, 2 configuration cannot be loaded / usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

import uvicorn

from home_dns import __version__
from home_dns.api.app import create_app
from home_dns.bootstrap import StartupRefusedError, build_runtime
from home_dns.config.filtering import (
    FilteringLoadResult,
    filtering_config_files,
    load_filtering_config,
)
from home_dns.config.loader import (
    ConfigFileScan,
    ConfigLoadError,
    LoadedConfig,
    default_config_dir,
    load_config,
    resolve_environment,
    scan_config_tree,
)
from home_dns.config.placeholders import Placeholder
from home_dns.config.readiness import ReadinessReport, evaluate_readiness
from home_dns.config.settings import Environment
from home_dns.config.storage import StorageConfig, load_storage_config, storage_config_files
from home_dns.core.blocklists import ArtifactFormatError, BlockEntry, parse_artifact
from home_dns.core.domains import InvalidDomainError
from home_dns.core.policy import PolicyEngine, UnknownGroupError
from home_dns.core.storage import StorageReport, plan_cleanup
from home_dns.pipeline.blocklists import Outcome, PipelineOptions, SourceReport, run_update
from home_dns.pipeline.fetch import Fetcher, HttpxFetcher
from home_dns.providers.base import ProviderError
from home_dns.providers.mock import MockDnsProvider
from home_dns.storage.artifacts import ArtifactStore, ArtifactStoreError
from home_dns.storage.backup import (
    BackupError,
    create_backup,
    list_backups,
    prune_backups,
    restore_backup,
    verify_backup,
)
from home_dns.storage.cleanup import execute_cleanup
from home_dns.storage.disk import DiskUsageProvider, SystemDiskUsage
from home_dns.storage.report import build_storage_report

EXIT_OK = 0
EXIT_NOT_READY = 1
EXIT_LOAD_ERROR = 2


def _add_config_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--env",
        choices=[e.value for e in Environment],
        default=None,
        help="environment (default: $HOME_DNS_ENV or development)",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help="configuration directory (default: $HOME_DNS_CONFIG_DIR or ./config)",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=None,
        help="validate this profile file instead of config/app/<env>.yaml",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="home-dns", description=__doc__)
    parser.add_argument("--version", action="version", version=f"home-dns {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate-config", help="validate configuration (read-only)")
    _add_config_arguments(validate)
    validate.add_argument("--format", choices=["text", "json"], default="text")
    validate.add_argument("--strict", action="store_true", help="treat warnings as errors")

    serve = commands.add_parser("serve", help="run the API (development only in A0)")
    _add_config_arguments(serve)

    blocklists = commands.add_parser("blocklists", help="blocklist pipeline (development only)")
    actions = blocklists.add_subparsers(dest="blocklists_command", required=True)
    update = actions.add_parser("update", help="download, validate and (with --apply) activate")
    _add_config_arguments(update)
    update.add_argument("--source", action="append", default=None, help="limit to source id(s)")
    update.add_argument("--apply", action="store_true", help="activate in the local artifact store")
    update.add_argument(
        "--accept-anomalies",
        action="store_true",
        help="continue past sanity anomalies after manual review (never the tripwire)",
    )
    update.add_argument("--format", choices=["text", "json"], default="text")
    status = actions.add_parser("status", help="show active and previous artifacts")
    _add_config_arguments(status)
    rollback = actions.add_parser("rollback", help="restore the previous artifact of a source")
    _add_config_arguments(rollback)
    rollback.add_argument("source")
    rollback.add_argument("--apply", action="store_true", help="perform the rollback")

    policy = commands.add_parser("policy", help="inspect the filtering policy (read-only)")
    policy_actions = policy.add_subparsers(dest="policy_command", required=True)
    explain = policy_actions.add_parser("explain", help="why a domain is allowed or blocked")
    _add_config_arguments(explain)
    explain.add_argument("--group", required=True, help="device group id, e.g. SMART-TV")
    explain.add_argument("domains", nargs="+", help="domain names to evaluate")
    explain.add_argument("--format", choices=["text", "json"], default="text")

    storage = commands.add_parser("storage", help="storage status, cleanup and backups")
    storage_actions = storage.add_subparsers(dest="storage_command", required=True)
    status = storage_actions.add_parser("status", help="disk usage, thresholds, categories")
    _add_config_arguments(status)
    status.add_argument("--format", choices=["text", "json"], default="text")
    cleanup = storage_actions.add_parser(
        "cleanup", help="run the cleanup appropriate for the current threshold band"
    )
    _add_config_arguments(cleanup)
    cleanup.add_argument("--apply", action="store_true", help="perform the cleanup")
    cleanup.add_argument("--format", choices=["text", "json"], default="text")
    verify = storage_actions.add_parser(
        "verify", help="verify backup checksums and blocklist artifact integrity"
    )
    _add_config_arguments(verify)
    verify.add_argument("--format", choices=["text", "json"], default="text")
    backup = storage_actions.add_parser(
        "backup", help="back up config/ (and the database, if one exists)"
    )
    _add_config_arguments(backup)
    backup.add_argument("--apply", action="store_true", help="write the backup")
    backup.add_argument("--format", choices=["text", "json"], default="text")
    restore = storage_actions.add_parser("restore", help="restore a named backup")
    _add_config_arguments(restore)
    restore.add_argument("name", help="backup name, e.g. backup-20260914T120000Z")
    restore.add_argument("--apply", action="store_true", help="perform the restore")
    return parser


def _load(args: argparse.Namespace) -> tuple[LoadedConfig, Path]:
    environment = resolve_environment(args.env)
    config_dir = args.config_dir or default_config_dir()
    return load_config(
        environment=environment, config_dir=config_dir, profile=args.profile
    ), config_dir


@dataclass(frozen=True)
class _Outcome:
    config: LoadedConfig
    report: ReadinessReport
    scans: list[ConfigFileScan]
    filtering: FilteringLoadResult | None
    filtering_error: str | None
    strict: bool
    storage: StorageConfig | None = None
    storage_error: str | None = None

    @property
    def filtering_ok(self) -> bool:
        if self.filtering_error is not None or self.filtering is None:
            return False
        return not self.filtering.errors and not (self.strict and self.filtering.warnings)

    @property
    def storage_ok(self) -> bool:
        return self.storage_error is None and self.storage is not None

    @property
    def ready(self) -> bool:
        return self.report.is_ready(strict=self.strict) and self.filtering_ok and self.storage_ok

    @property
    def load_failed(self) -> bool:
        broken_filtering = self.filtering_error is not None or bool(
            self.filtering and self.filtering.errors
        )
        return (
            broken_filtering
            or self.storage_error is not None
            or any(scan.error for scan in self.scans)
        )


def _filtering_summary(result: FilteringLoadResult) -> dict[str, int]:
    cfg = result.config
    rules = [*cfg.allow, *cfg.deny, *cfg.regex]
    return {
        "groups": len(cfg.groups),
        "policies": len(cfg.policies),
        "sources": len(cfg.sources),
        "allow_rules": len(cfg.allow),
        "deny_rules": len(cfg.deny),
        "regex_rules": len(cfg.regex),
        "expired_rules": sum(1 for r in rules if not r.is_active(result.evaluated_at)),
        "rules_with_expiry": sum(1 for r in rules if r.expires_at is not None),
        "protected_domains": len(cfg.protected_domains()),
    }


def _print_text(outcome: _Outcome, out: TextIO) -> None:
    config, report = outcome.config, outcome.report
    print("home-dns validate-config", file=out)
    print(f"  environment : {config.environment.value}", file=out)
    print(f"  profile     : {config.profile_path}", file=out)
    print(f"  provider    : {config.settings.dns_provider.kind.value}", file=out)
    print("\nSettings:", file=out)
    for f in report.findings:
        print(f"  {f.severity.value:<8}{f.status.value:<21} {f.path:<45} {f.message}", file=out)

    print("\nFiltering configuration:", file=out)
    if outcome.filtering_error is not None:
        print(f"  error   {outcome.filtering_error}", file=out)
    elif outcome.filtering is not None:
        summary = " · ".join(f"{k}={v}" for k, v in _filtering_summary(outcome.filtering).items())
        print(f"  {summary}", file=out)
        print("  (allow[i] / deny[i] / regex[i] = index in config/rules/<kind>.yaml)", file=out)
        for issue in outcome.filtering.issues:
            print(f"  {issue.level:<8}{issue.location:<30} {issue.message}", file=out)

    print("\nStorage configuration:", file=out)
    if outcome.storage_error is not None:
        print(f"  error   {outcome.storage_error}", file=out)
    elif outcome.storage is not None:
        t, r = outcome.storage.thresholds, outcome.storage.retention
        print(
            f"  thresholds: healthy<{t.warning_from:g}% warning<{t.auto_cleanup_from:g}%"
            f" auto_cleanup<{t.emergency_from:g}% emergency>={t.emergency_from:g}%",
            file=out,
        )
        print(
            f"  retention: logs={r.logs_max_bytes}B x{r.logs_backup_count} "
            f"temp={r.temp_max_age_hours}h backups_keep={r.backups_keep} "
            f"query_history={r.query_history_days}d",
            file=out,
        )

    print("\nOther config files (no schema yet):", file=out)
    for scan in outcome.scans:
        if scan.error:
            print(f"  error   {scan.error}", file=out)
        else:
            extra = f"  placeholders: {', '.join(scan.placeholders)}" if scan.placeholders else ""
            print(f"  ok      {scan.path}{extra}", file=out)

    filtering_errors = len(outcome.filtering.errors) if outcome.filtering else 0
    filtering_warnings = len(outcome.filtering.warnings) if outcome.filtering else 0
    errors = (
        len(report.errors)
        + filtering_errors
        + (outcome.filtering_error is not None)
        + (outcome.storage_error is not None)
    )
    warnings = len(report.warnings) + filtering_warnings
    verdict = "READY" if outcome.ready else "NOT READY"
    print(f"\nResult: {verdict} — {errors} error(s), {warnings} warning(s)", file=out)


def _print_json(outcome: _Outcome, out: TextIO) -> None:
    report, filtering = outcome.report, outcome.filtering
    payload = {
        "environment": outcome.config.environment.value,
        "profile": str(outcome.config.profile_path),
        "provider": outcome.config.settings.dns_provider.kind.value,
        "ready": outcome.ready,
        "errors": len(report.errors),
        "warnings": len(report.warnings),
        "findings": [
            {
                "path": f.path,
                "status": f.status.value,
                "severity": f.severity.value,
                "message": f.message,
            }
            for f in report.findings
        ],
        "filtering": {
            "error": outcome.filtering_error,
            "summary": _filtering_summary(filtering) if filtering else None,
            "issues": [
                {"level": i.level, "location": i.location, "message": i.message}
                for i in (filtering.issues if filtering else ())
            ],
        },
        "storage": {
            "error": outcome.storage_error,
            "thresholds": (outcome.storage.thresholds.model_dump() if outcome.storage else None),
            "retention": (outcome.storage.retention.model_dump() if outcome.storage else None),
        },
        "config_files": [
            {"path": str(s.path), "placeholders": list(s.placeholders), "error": s.error}
            for s in outcome.scans
        ],
    }
    json.dump(payload, out, indent=2)
    out.write("\n")


def _validate_config(
    args: argparse.Namespace, out: TextIO, err: TextIO, now: Callable[[], datetime]
) -> int:
    try:
        config, config_dir = _load(args)
    except ConfigLoadError as exc:
        print(f"configuration error: {exc}", file=err)
        return EXIT_LOAD_ERROR
    report = evaluate_readiness(config.settings, config.secrets, config.environment)

    filtering: FilteringLoadResult | None = None
    filtering_error: str | None = None
    try:
        filtering = load_filtering_config(config_dir, now=now())
    except ConfigLoadError as exc:
        filtering_error = str(exc)

    storage: StorageConfig | None = None
    storage_error: str | None = None
    try:
        storage = load_storage_config(config_dir)
    except ConfigLoadError as exc:
        storage_error = str(exc)

    exclude = [*filtering_config_files(config_dir), *storage_config_files(config_dir)]
    scans = scan_config_tree(config_dir, exclude=exclude) if config_dir.is_dir() else []

    outcome = _Outcome(
        config, report, scans, filtering, filtering_error, args.strict, storage, storage_error
    )
    (_print_json if args.format == "json" else _print_text)(outcome, out)
    if outcome.load_failed:
        return EXIT_LOAD_ERROR
    return EXIT_OK if outcome.ready else EXIT_NOT_READY


def _serve(args: argparse.Namespace, err: TextIO) -> int:
    try:
        config, _ = _load(args)
    except ConfigLoadError as exc:
        print(f"configuration error: {exc}", file=err)
        return EXIT_LOAD_ERROR
    if config.environment is Environment.PRODUCTION:
        print("serve is development-only until API authentication exists (phase A7)", file=err)
        return EXIT_NOT_READY
    try:
        runtime = build_runtime(config)
    except (StartupRefusedError, ProviderError) as exc:
        print(f"startup refused: {exc}", file=err)
        return EXIT_NOT_READY
    api = config.settings.api
    uvicorn.run(
        create_app(environment=config.environment, provider=runtime.provider),
        host=str(api.bind_host),
        port=int(str(api.port)),
    )
    return EXIT_OK


_SUCCESS_OUTCOMES = {Outcome.ACTIVATED, Outcome.WOULD_ACTIVATE, Outcome.UNCHANGED}


def _print_source_report(report: SourceReport, dry_run: bool, out: TextIO) -> None:
    suffix = " (dry-run)" if dry_run else ""
    print(f"{report.source_id}: {report.outcome.value}{suffix}", file=out)
    for attempt in report.attempts:
        verdict = "accepted" if attempt.accepted else f"rejected: {attempt.reason}"
        print(f"  attempt {attempt.role} {attempt.url} — {verdict}", file=out)
        for result in attempt.stages:
            print(f"    {result.status.value:<8}{result.stage.value:<28}{result.detail}", file=out)
    for result in report.stages:
        print(f"  {result.status.value:<10}{result.stage.value:<28}{result.detail}", file=out)
    for alert in report.alerts:
        print(f"  alert [{alert.severity}] {alert.event}: {alert.message}", file=out)


def _blocklists(
    args: argparse.Namespace,
    out: TextIO,
    err: TextIO,
    now: Callable[[], datetime],
    fetcher: Fetcher | None,
) -> int:
    try:
        config, config_dir = _load(args)
        filtering = load_filtering_config(config_dir, now=now())
    except ConfigLoadError as exc:
        print(f"configuration error: {exc}", file=err)
        return EXIT_LOAD_ERROR
    if config.environment is Environment.PRODUCTION:
        print(
            "blocklist pipeline is development-only until production activation (phase C3)",
            file=err,
        )
        return EXIT_NOT_READY
    if filtering.errors:
        print("filtering configuration has errors; run validate-config", file=err)
        return EXIT_LOAD_ERROR
    data_dir = config.settings.paths.data_dir
    if isinstance(data_dir, Placeholder):
        print(f"paths.data_dir is unresolved ({data_dir.token})", file=err)
        return EXIT_NOT_READY
    store = ArtifactStore(config.resolve(data_dir) / "blocklists")
    sources = filtering.config.sources

    if args.blocklists_command == "status":
        for source in sources:
            state = store.state(source.id)
            line = (
                f"{source.id}: current={state.current or '-'} previous={state.previous or '-'}"
                f" backup={state.backup or '-'}"
            )
            if state.current:
                meta = store.read(source.id, state.current).metadata
                line += (
                    f" version={meta.get('version')} entries={meta.get('valid_entries')}"
                    f" activated_at={meta.get('activated_at')}"
                )
            print(line, file=out)
        return EXIT_OK

    if args.blocklists_command == "rollback":
        try:
            change = store.rollback(args.source, dry_run=not args.apply)
        except ArtifactStoreError as exc:
            print(f"rollback refused: {exc}", file=err)
            return EXIT_NOT_READY
        mode = "rolled back" if args.apply else "dry-run: would roll back"
        print(
            f"{args.source}: {mode} current {change.before.current} -> {change.after.current}",
            file=out,
        )
        return EXIT_OK

    selected = [s for s in sources if not args.source or s.id in args.source]
    unknown = sorted(set(args.source or ()) - {s.id for s in sources})
    if unknown:
        print(f"unknown source(s): {', '.join(unknown)}", file=err)
        return EXIT_LOAD_ERROR
    options = PipelineOptions(
        now=now(), dry_run=not args.apply, accept_anomalies=args.accept_anomalies
    )
    reports = run_update(
        selected,
        protected=filtering.config.protected_domains(),
        fetcher=fetcher or HttpxFetcher(),
        store=store,
        test_provider_factory=MockDnsProvider,
        options=options,
    )
    if args.format == "json":
        json.dump([r.to_dict() for r in reports], out, indent=2, default=str)
        out.write("\n")
    else:
        for report in reports:
            _print_source_report(report, options.dry_run, out)
    return EXIT_OK if all(r.outcome in _SUCCESS_OUTCOMES for r in reports) else EXIT_NOT_READY


def _policy_explain(
    args: argparse.Namespace, out: TextIO, err: TextIO, now: Callable[[], datetime]
) -> int:
    try:
        config, config_dir = _load(args)
        filtering = load_filtering_config(config_dir, now=now())
    except ConfigLoadError as exc:
        print(f"configuration error: {exc}", file=err)
        return EXIT_LOAD_ERROR
    if filtering.errors:
        print("filtering configuration has errors; run validate-config", file=err)
        return EXIT_LOAD_ERROR

    blocklists: dict[str, frozenset[BlockEntry]] = {}
    notes: list[str] = []
    data_dir = config.settings.paths.data_dir
    if isinstance(data_dir, Placeholder):
        notes.append(f"paths.data_dir unresolved ({data_dir.token}); blocklists not evaluated")
    else:
        store = ArtifactStore(config.resolve(data_dir) / "blocklists")
        for source in filtering.config.sources:
            try:
                artifact = store.current(source.id)
                if artifact is None:
                    notes.append(f"{source.id}: no active artifact; list not evaluated")
                else:
                    blocklists[source.id] = parse_artifact(artifact.text)
            except (ArtifactStoreError, ArtifactFormatError) as exc:
                notes.append(f"{source.id}: active artifact unreadable ({exc}); list not evaluated")

    engine = PolicyEngine(filtering.config, blocklists, now=now())
    try:
        decisions = [engine.decide(args.group, domain) for domain in args.domains]
    except (UnknownGroupError, InvalidDomainError) as exc:
        print(f"invalid input: {exc}", file=err)
        return EXIT_LOAD_ERROR

    if args.format == "json":
        payload = {
            "group": args.group,
            "policy_sources": list(engine.sources_for(args.group)),
            "notes": notes,
            "decisions": [
                {
                    "domain": d.domain,
                    "verdict": d.verdict.value,
                    "reason": d.reason.value,
                    "detail": d.detail,
                    "matched": list(d.matched),
                }
                for d in decisions
            ],
        }
        json.dump(payload, out, indent=2)
        out.write("\n")
    else:
        print(f"group {args.group} uses: {', '.join(engine.sources_for(args.group))}", file=out)
        for note in notes:
            print(f"  note: {note}", file=out)
        for d in decisions:
            print(f"{d.domain}: {d.verdict.value} ({d.reason.value}) — {d.detail}", file=out)
    return EXIT_OK


_DATABASE_FILENAME = "home-dns.db"  # convention; A7 owns the schema, not the filename


def _resolved_paths(config: LoadedConfig) -> dict[str, Path] | None:
    paths = config.settings.paths
    fields = {
        "data_dir": paths.data_dir,
        "log_dir": paths.log_dir,
        "backup_dir": paths.backup_dir,
        "tmp_dir": paths.tmp_dir,
    }
    if any(isinstance(v, Placeholder) for v in fields.values()):
        return None
    return {name: config.resolve(value) for name, value in fields.items()}  # type: ignore[arg-type]


def _load_artifact_source_ids(config_dir: Path, now: datetime) -> list[str]:
    try:
        filtering = load_filtering_config(config_dir, now=now)
    except ConfigLoadError:
        return []  # storage status/cleanup still works; artifact counts simply unavailable
    return [s.id for s in filtering.config.sources]


def _print_storage_report(report: StorageReport, out: TextIO) -> None:
    print(
        f"disk: {report.disk.used_bytes}/{report.disk.total_bytes} bytes "
        f"({report.disk.used_percent:g}%) — state={report.state.value}",
        file=out,
    )
    if report.event:
        print(f"  alert event if this state persists: {report.event}", file=out)
    print(f"  recommended action: {report.recommended_action.value}", file=out)
    for category in report.categories:
        present = "" if category.exists else "  (missing)"
        print(
            f"  category {category.name:<10} {category.bytes} bytes  {category.path}{present}",
            file=out,
        )
    print(
        f"  backups: {report.backup_count} valid, "
        f"last {report.last_backup_at.isoformat() if report.last_backup_at else 'never'}"
        f" (age {report.backup_age_seconds:.0f}s)"
        if report.last_backup_at
        else f"  backups: {report.backup_count} valid, last never",
        file=out,
    )
    if report.artifact_counts:
        counts = ", ".join(f"{k}={v}" for k, v in report.artifact_counts.items())
        print(f"  blocklist artifacts: {counts}", file=out)


def _storage(
    args: argparse.Namespace,
    out: TextIO,
    err: TextIO,
    now: Callable[[], datetime],
    disk: DiskUsageProvider | None = None,
) -> int:
    try:
        config, config_dir = _load(args)
        storage_config = load_storage_config(config_dir)
    except ConfigLoadError as exc:
        print(f"configuration error: {exc}", file=err)
        return EXIT_LOAD_ERROR
    if config.environment is Environment.PRODUCTION:
        print(
            "storage commands are development-only until production activation (phase C3)",
            file=err,
        )
        return EXIT_NOT_READY

    paths = _resolved_paths(config)
    if paths is None:
        print("one or more paths.* settings are unresolved placeholders", file=err)
        return EXIT_NOT_READY
    data_dir, log_dir, backup_dir, tmp_dir = (
        paths["data_dir"],
        paths["log_dir"],
        paths["backup_dir"],
        paths["tmp_dir"],
    )
    store = ArtifactStore(data_dir / "blocklists")
    artifact_source_ids = _load_artifact_source_ids(config_dir, now())
    disk_provider = disk or SystemDiskUsage()

    if args.storage_command == "status":
        report = build_storage_report(
            root=data_dir,
            categories={"data": data_dir, "logs": log_dir, "backups": backup_dir, "tmp": tmp_dir},
            disk=disk_provider,
            thresholds=storage_config.thresholds,
            backup_dir=backup_dir,
            artifact_store=store,
            artifact_sources=artifact_source_ids,
            now=now(),
        )
        if args.format == "json":
            json.dump(report.model_dump(mode="json"), out, indent=2)
            out.write("\n")
        else:
            _print_storage_report(report, out)
        return EXIT_OK

    if args.storage_command == "cleanup":
        report = build_storage_report(
            root=data_dir,
            categories={"data": data_dir, "logs": log_dir, "backups": backup_dir, "tmp": tmp_dir},
            disk=disk_provider,
            thresholds=storage_config.thresholds,
            backup_dir=backup_dir,
            artifact_store=store,
            artifact_sources=artifact_source_ids,
            now=now(),
        )
        plan = plan_cleanup(report.state)
        cleanup_result = execute_cleanup(
            plan,
            tmp_dir=tmp_dir,
            backup_dir=backup_dir,
            artifact_store=store,
            artifact_sources=artifact_source_ids,
            retention=storage_config.retention,
            now=now(),
            dry_run=not args.apply,
        )
        if args.format == "json":
            json.dump(
                {
                    "state": plan.state.value,
                    "action": plan.action.value,
                    "dry_run": not args.apply,
                    "steps": [
                        {"target": s.target, "removed": list(s.removed)}
                        for s in cleanup_result.steps
                    ],
                },
                out,
                indent=2,
            )
            out.write("\n")
        else:
            suffix = "" if args.apply else " (dry-run)"
            print(f"state={plan.state.value} action={plan.action.value}{suffix}", file=out)
            for step in cleanup_result.steps:
                print(f"  {step.target}: {step.description}", file=out)
                for name in step.removed:
                    print(f"    removed: {name}", file=out)
        return EXIT_OK

    if args.storage_command == "verify":
        problems: list[str] = []
        for info in list_backups(backup_dir):
            if not info.valid:
                problems.append(f"backup {info.name}: {info.error}")
                continue
            verification = verify_backup(info.path)
            if not verification.ok:
                problems.append(f"backup {info.name}: {len(verification.mismatches)} mismatch(es)")
        for source_id in artifact_source_ids:
            state = store.state(source_id)
            for label, sha in (
                ("current", state.current),
                ("previous", state.previous),
                ("backup", state.backup),
            ):
                if sha is None:
                    continue
                try:
                    store.read(source_id, sha)
                except ArtifactStoreError as exc:
                    problems.append(f"artifact {source_id}/{label}: {exc}")
        db_path = data_dir / _DATABASE_FILENAME
        if db_path.is_file():
            from home_dns.storage.sqlite import check_integrity, open_database

            connection = open_database(db_path)
            try:
                integrity = check_integrity(connection)
            finally:
                connection.close()
            if not integrity.ok:
                problems.append(f"database {db_path}: {', '.join(integrity.messages)}")
        if args.format == "json":
            json.dump({"ok": not problems, "problems": problems}, out, indent=2)
            out.write("\n")
        else:
            print(f"verify: {'ok' if not problems else 'PROBLEMS FOUND'}", file=out)
            for problem in problems:
                print(f"  {problem}", file=out)
        return EXIT_OK if not problems else EXIT_NOT_READY

    if args.storage_command == "backup":
        sources: dict[str, Path] = {"config": config_dir}
        db_path = data_dir / _DATABASE_FILENAME
        db_snapshot_dir: Path | None = None
        if db_path.is_file():
            from home_dns.storage.sqlite import backup_database, open_database

            db_snapshot_dir = tmp_dir / f".db-snapshot-{int(now().timestamp())}"
            connection = open_database(db_path)
            try:
                if args.apply:
                    db_snapshot_dir.mkdir(parents=True, exist_ok=True)
                    backup_database(connection, db_snapshot_dir / _DATABASE_FILENAME, dry_run=False)
                    sources["database"] = db_snapshot_dir
            finally:
                connection.close()
        backup_result = create_backup(sources, backup_dir, now=now(), dry_run=not args.apply)
        if db_snapshot_dir is not None and db_snapshot_dir.exists():
            import shutil as _shutil

            _shutil.rmtree(db_snapshot_dir, ignore_errors=True)
        if not args.apply:
            prune_preview = prune_backups(backup_dir, keep=storage_config.retention.backups_keep)
        else:
            prune_preview = prune_backups(
                backup_dir, keep=storage_config.retention.backups_keep, dry_run=False
            )
        if args.format == "json":
            json.dump(
                {
                    "dry_run": not args.apply,
                    "name": backup_result.name,
                    "files": len(backup_result.manifest.entries),
                    "bytes": backup_result.manifest.total_bytes,
                    "pruned": list(prune_preview.removed),
                },
                out,
                indent=2,
            )
            out.write("\n")
        else:
            suffix = "" if args.apply else " (dry-run)"
            print(
                f"{backup_result.name}: {len(backup_result.manifest.entries)} file(s), "
                f"{backup_result.manifest.total_bytes} bytes{suffix}",
                file=out,
            )
            for name in prune_preview.removed:
                print(f"  pruned: {name}", file=out)
        return EXIT_OK

    if args.storage_command == "restore":
        backup_path = backup_dir / args.name
        try:
            restore_result = restore_backup(
                backup_path, targets={"config": config_dir}, dry_run=not args.apply
            )
        except BackupError as exc:
            print(f"restore refused: {exc}", file=err)
            return EXIT_NOT_READY
        suffix = "" if args.apply else " (dry-run)"
        print(f"{args.name}: {len(restore_result.restored)} file(s) restored{suffix}", file=out)
        return EXIT_OK

    return EXIT_LOAD_ERROR  # unreachable: argparse enforces storage_command choices


def main(
    argv: Sequence[str] | None = None,
    *,
    out: TextIO | None = None,
    err: TextIO | None = None,
    now: Callable[[], datetime] | None = None,
    fetcher: Fetcher | None = None,
    disk: DiskUsageProvider | None = None,
) -> int:
    out = out or sys.stdout
    err = err or sys.stderr
    clock = now or (lambda: datetime.now(UTC))
    args = _build_parser().parse_args(argv)
    if args.command == "validate-config":
        return _validate_config(args, out, err, clock)
    if args.command == "blocklists":
        return _blocklists(args, out, err, clock, fetcher)
    if args.command == "policy":
        return _policy_explain(args, out, err, clock)
    if args.command == "storage":
        return _storage(args, out, err, clock, disk)
    return _serve(args, err)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
