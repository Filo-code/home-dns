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
from home_dns.pipeline.blocklists import Outcome, PipelineOptions, SourceReport, run_update
from home_dns.pipeline.fetch import Fetcher, HttpxFetcher
from home_dns.providers.base import ProviderError
from home_dns.providers.mock import MockDnsProvider
from home_dns.storage.artifacts import ArtifactStore, ArtifactStoreError

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

    @property
    def filtering_ok(self) -> bool:
        if self.filtering_error is not None or self.filtering is None:
            return False
        return not self.filtering.errors and not (self.strict and self.filtering.warnings)

    @property
    def ready(self) -> bool:
        return self.report.is_ready(strict=self.strict) and self.filtering_ok

    @property
    def load_failed(self) -> bool:
        broken_filtering = self.filtering_error is not None or bool(
            self.filtering and self.filtering.errors
        )
        return broken_filtering or any(scan.error for scan in self.scans)


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

    print("\nOther config files (no schema yet):", file=out)
    for scan in outcome.scans:
        if scan.error:
            print(f"  error   {scan.error}", file=out)
        else:
            extra = f"  placeholders: {', '.join(scan.placeholders)}" if scan.placeholders else ""
            print(f"  ok      {scan.path}{extra}", file=out)

    filtering_errors = len(outcome.filtering.errors) if outcome.filtering else 0
    filtering_warnings = len(outcome.filtering.warnings) if outcome.filtering else 0
    errors = len(report.errors) + filtering_errors + (outcome.filtering_error is not None)
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
    scans = (
        scan_config_tree(config_dir, exclude=filtering_config_files(config_dir))
        if config_dir.is_dir()
        else []
    )

    outcome = _Outcome(config, report, scans, filtering, filtering_error, args.strict)
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


def main(
    argv: Sequence[str] | None = None,
    *,
    out: TextIO | None = None,
    err: TextIO | None = None,
    now: Callable[[], datetime] | None = None,
    fetcher: Fetcher | None = None,
) -> int:
    out = out or sys.stdout
    err = err or sys.stderr
    clock = now or (lambda: datetime.now(UTC))
    args = _build_parser().parse_args(argv)
    if args.command == "validate-config":
        return _validate_config(args, out, err, clock)
    if args.command == "blocklists":
        return _blocklists(args, out, err, clock, fetcher)
    return _serve(args, err)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
