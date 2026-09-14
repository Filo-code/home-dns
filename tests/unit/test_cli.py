import argparse
import io
import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from home_dns import cli
from tests.conftest import DEV_PROFILE, PROD_READY_PROFILE

MakeConfigDir = Callable[..., Path]


def _run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(list(argv), out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def test_validate_committed_development_config_exits_0() -> None:
    code, out, _ = _run("validate-config", "--env", "development")
    assert code == 0
    assert "Result: READY" in out


def test_validate_production_example_exits_1_and_lists_placeholders(repo_config_dir: Path) -> None:
    code, out, _ = _run(
        "validate-config",
        "--env",
        "production",
        "--profile",
        str(repo_config_dir / "app" / "production.example.yaml"),
    )
    assert code == 1
    assert "<<AUDIT:paths.data_dir>>" in out
    assert "<<REQUIRED:api.port>>" in out
    assert "HOME_DNS_PIHOLE_APP_PASSWORD is not set" in out
    assert "Result: NOT READY" in out


def test_secret_values_never_appear_in_output(
    repo_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME_DNS_PIHOLE_APP_PASSWORD", "very-secret-value")
    for fmt in ("text", "json"):
        _, out, err = _run(
            "validate-config",
            "--env",
            "production",
            "--format",
            fmt,
            "--profile",
            str(repo_config_dir / "app" / "production.example.yaml"),
        )
        assert "very-secret-value" not in out + err


def test_json_output(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    code, out, _ = _run("validate-config", "--config-dir", str(config_dir), "--format", "json")
    payload = json.loads(out)
    assert code == 0
    assert payload["ready"] is True
    assert payload["environment"] == "development"
    assert {f["path"] for f in payload["findings"]} >= {"api.port", "dns_provider.kind"}


def test_environment_selected_via_env_var(
    make_config_dir: MakeConfigDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    monkeypatch.setenv("HOME_DNS_ENV", "production")
    code, _, err = _run("validate-config", "--config-dir", str(config_dir))
    assert code == 2
    assert "file not found" in err


def test_load_errors_exit_2(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE, env="production")
    code, _, err = _run("validate-config", "--env", "production", "--config-dir", str(config_dir))
    assert code == 2
    assert "configuration error" in err


def test_unknown_environment_exits_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME_DNS_ENV", "staging")
    code, _, err = _run("validate-config")
    assert code == 2
    assert "unknown environment" in err


def test_hygiene_problem_in_other_config_file_exits_2(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE, **{"telegram__alerts.yaml": "api_key: x\n"})
    code, out, _ = _run("validate-config", "--config-dir", str(config_dir))
    assert code == 2
    assert "secret-like keys" in out


def test_strict_turns_warnings_into_failure(
    make_config_dir: MakeConfigDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME_DNS_PIHOLE_APP_PASSWORD", "x")
    text = PROD_READY_PROFILE.replace("bind_host: 192.0.2.53", "bind_host: 0.0.0.0")
    config_dir = make_config_dir(text, env="production")
    base = ("validate-config", "--env", "production", "--config-dir", str(config_dir))
    assert _run(*base)[0] == 0
    assert _run(*base, "--strict")[0] == 1


def test_validate_config_does_not_write_files(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    before = sorted(p for p in config_dir.parent.rglob("*"))
    _run("validate-config", "--config-dir", str(config_dir))
    assert sorted(p for p in config_dir.parent.rglob("*")) == before


def test_serve_refuses_production(repo_config_dir: Path) -> None:
    code, _, err = _run(
        "serve",
        "--env",
        "production",
        "--profile",
        str(repo_config_dir / "app" / "production.example.yaml"),
    )
    assert code == 1
    assert "development-only" in err


def test_serve_load_error_exits_2(tmp_path: Path) -> None:
    code, _, _ = _run("serve", "--config-dir", str(tmp_path))
    assert code == 2


def test_serve_refuses_unready_development_config(make_config_dir: MakeConfigDir) -> None:
    text = DEV_PROFILE.replace("port: 8080", 'port: "<<REQUIRED:api.port>>"')
    code, _, err = _run("serve", "--config-dir", str(make_config_dir(text)))
    assert code == 1
    assert "startup refused" in err


def test_serve_development_starts_uvicorn_on_configured_address(
    make_config_dir: MakeConfigDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []
    apps: list[Any] = []
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kw: (apps.append(app), calls.append(kw)))
    config_dir = make_config_dir(DEV_PROFILE)
    _set_password(monkeypatch, config_dir, "admin", "admin", "long enough password")
    code, _, _ = _run("serve", "--config-dir", str(config_dir))
    assert code == 0
    assert calls == [{"host": "127.0.0.1", "port": 8080}]
    paths = set(apps[0].openapi()["paths"])
    assert {"/api/v1/health", "/api/v1/auth/login", "/api/v1/overview"} <= paths


def _set_password(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path, username: str, role: str, password: str
) -> tuple[int, str, str]:
    monkeypatch.setattr(cli, "hash_password", _fast_hash)
    monkeypatch.setattr("sys.stdin", io.StringIO(password + "\n"))
    return _run(
        "auth", "set-password", "--config-dir", str(config_dir),
        "--username", username, "--role", role, "--password-stdin",
    )  # fmt: skip


def _fast_hash(password: str) -> str:
    from home_dns.core.auth import ScryptParams, hash_password

    return hash_password(password, params=ScryptParams(n=2**10))


def test_serve_refuses_without_an_admin_user(
    make_config_dir: MakeConfigDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kw: pytest.fail("must not start"))
    config_dir = make_config_dir(DEV_PROFILE)
    _set_password(monkeypatch, config_dir, "family", "viewer", "long enough password")
    code, _, err = _run("serve", "--config-dir", str(config_dir))
    assert code == 1
    assert "no dashboard admin user" in err


def test_serve_refuses_filtering_errors(
    make_config_dir: MakeConfigDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "load_filtering_config", lambda *a, **k: _FilteringWithErrors())
    code, _, err = _run("serve", "--config-dir", str(make_config_dir(DEV_PROFILE)))
    assert code == 1
    assert "filtering configuration has errors" in err


class _FilteringWithErrors:
    errors = ("broken",)


def test_serve_storage_config_error_exits_2(make_config_dir: MakeConfigDir) -> None:
    code, _, err = _run("serve", "--config-dir", str(make_config_dir(DEV_PROFILE, storage=False)))
    assert code == 2
    assert "configuration error" in err


# ------------------------------------------------------------------------- A7: auth users


def test_auth_set_password_and_list_users(
    make_config_dir: MakeConfigDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    code, out, _ = _set_password(monkeypatch, config_dir, "anna", "admin", "long enough password")
    assert code == 0 and "sessions revoked" in out
    assert "long enough password" not in out
    _set_password(monkeypatch, config_dir, "family", "viewer", "another long password")
    code, out, _ = _run("auth", "list-users", "--config-dir", str(config_dir))
    assert code == 0
    assert out.splitlines() == ["anna\tadmin", "family\tviewer"]


def test_auth_rejects_weak_password_and_bad_username(
    make_config_dir: MakeConfigDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    code, _, err = _set_password(monkeypatch, config_dir, "anna", "admin", "short")
    assert code == 1 and "at least 12" in err
    code, _, err = _set_password(
        monkeypatch, config_dir, "Anna Rossi", "admin", "long enough password"
    )
    assert code == 2 and "invalid username" in err
    assert _run("auth", "list-users", "--config-dir", str(config_dir))[1] == ""


def test_auth_interactive_prompt_requires_matching_passwords(
    make_config_dir: MakeConfigDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    monkeypatch.setattr(cli, "hash_password", _fast_hash)
    answers = iter(["long enough password", "different password!"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: next(answers))
    argv = (
        "auth",
        "set-password",
        "--config-dir",
        str(config_dir),
        "--username",
        "anna",
        "--role",
        "admin",
    )
    code, _, err = _run(*argv)
    assert code == 1 and "do not match" in err
    answers = iter(["long enough password", "long enough password"])
    assert _run(*argv)[0] == 0


def test_auth_refuses_production_and_placeholders(
    repo_config_dir: Path, make_config_dir: MakeConfigDir
) -> None:
    code, _, err = _run(
        "auth", "list-users", "--env", "production",
        "--profile", str(repo_config_dir / "app" / "production.example.yaml"),
    )  # fmt: skip
    assert code == 1 and "development-only" in err
    text = DEV_PROFILE.replace("data_dir: .local/data", 'data_dir: "<<AUDIT:paths.data_dir>>"')
    code, _, err = _run("auth", "list-users", "--config-dir", str(make_config_dir(text)))
    assert code == 1 and "placeholders" in err
    assert _run("auth", "list-users", "--config-dir", "/nonexistent-config-dir")[0] == 2


def test_serve_dashboard_status_reads_maintenance_state(
    make_config_dir: MakeConfigDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    from home_dns.core.monitoring import Incident, IncidentState
    from home_dns.storage.artifacts import ArtifactStore
    from home_dns.storage.monitoring import MonitoringStore

    apps: list[Any] = []
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kw: apps.append(app))
    config_dir = make_config_dir(DEV_PROFILE)
    data_dir = config_dir.parent / ".local" / "data"
    _set_password(monkeypatch, config_dir, "admin", "admin", "long enough password")
    source_id = cli.load_filtering_config(config_dir, now=FIXED_NOW).config.sources[0].id
    store = ArtifactStore(data_dir / "blocklists")
    store.activate(
        source_id, "ads.example\n", {"activated_at": "2026-09-13T04:00:00+00:00"}, dry_run=False
    )
    MonitoringStore(data_dir / "monitoring").save_incident(
        Incident("dns_down", IncidentState.INCIDENT), dry_run=False
    )
    (data_dir / "monitoring" / "incidents" / "Bad Name.json").write_text("{}")
    assert _run("serve", "--config-dir", str(config_dir))[0] == 0
    status = apps[0].state.dashboard.status()
    assert status.last_blocklist_update_at == datetime(2026, 9, 13, 4, tzinfo=UTC)
    assert [i.check_name for i in status.incidents] == ["dns_down"]
    assert status.last_backup_at is None
    assert apps[0].state.dashboard.collector is not None


def test_serve_dashboard_status_tolerates_corrupt_state(
    make_config_dir: MakeConfigDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    apps: list[Any] = []
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kw: apps.append(app))
    config_dir = make_config_dir(DEV_PROFILE)
    data_dir = config_dir.parent / ".local" / "data"
    _set_password(monkeypatch, config_dir, "admin", "admin", "long enough password")
    source_id = cli.load_filtering_config(config_dir, now=FIXED_NOW).config.sources[0].id
    (data_dir / "blocklists" / source_id).mkdir(parents=True)
    (data_dir / "blocklists" / source_id / "state.json").write_text("not json")
    (data_dir / "monitoring" / "incidents").mkdir(parents=True)
    (data_dir / "monitoring" / "incidents" / "dns.json").write_text("not json")
    assert _run("serve", "--config-dir", str(config_dir))[0] == 0
    status = apps[0].state.dashboard.status()
    assert status.last_blocklist_update_at is None and status.incidents == ()


# ------------------------------------------------------------------ A1: filtering config

FIXED_NOW = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


def _run_at(now: datetime, *argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(list(argv), out=out, err=err, now=lambda: now)
    return code, out.getvalue(), err.getvalue()


def test_repository_filtering_config_is_reported() -> None:
    code, out, _ = _run("validate-config")
    assert code == 0
    assert "groups=6" in out
    assert "policies=4" in out
    assert "sources=4" in out
    assert "no protected domains defined" not in out


def test_repository_config_passes_strict_now_that_protected_domains_exist() -> None:
    assert _run("validate-config", "--strict")[0] == 0


def test_filtering_schema_error_exits_2(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE, **{"groups__groups.yaml": "schema_version: 1\n"})
    code, out, _ = _run("validate-config", "--config-dir", str(config_dir))
    assert code == 2
    assert "groups/groups.yaml" in out


def test_missing_filtering_files_exit_2(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE, filtering=False)
    code, out, _ = _run("validate-config", "--config-dir", str(config_dir), "--format", "json")
    assert code == 2
    assert "file not found" in json.loads(out)["filtering"]["error"]


_EXPIRING_ALLOW = """\
schema_version: 1
rules:
  - domain: tvstore.example
    reason: TV store catalogue fails
    author: owner
    created_at: 2026-09-13
    expires_at: 2026-09-20T12:00:00+00:00
    groups: [SMART-TV]
    source: manual troubleshooting
"""


def test_expiring_rule_is_active_then_reported_as_expired(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE, **{"rules__allow.yaml": _EXPIRING_ALLOW})
    args = ("validate-config", "--config-dir", str(config_dir), "--format", "json")

    code, out, _ = _run_at(FIXED_NOW, *args)
    summary = json.loads(out)["filtering"]["summary"]
    assert code == 0
    assert summary["allow_rules"] == 1 and summary["rules_with_expiry"] == 1
    assert summary["expired_rules"] == 0

    code, out, _ = _run_at(datetime(2026, 9, 21, tzinfo=UTC), *args)
    payload = json.loads(out)["filtering"]
    assert code == 0
    assert payload["summary"]["expired_rules"] == 1
    assert any(i["level"] == "info" and "expired" in i["message"] for i in payload["issues"])


def test_cross_reference_error_exits_2(make_config_dir: MakeConfigDir) -> None:
    bad_allow = _EXPIRING_ALLOW.replace("[SMART-TV]", "[GHOST]")
    config_dir = make_config_dir(DEV_PROFILE, **{"rules__allow.yaml": bad_allow})
    code, out, _ = _run_at(FIXED_NOW, "validate-config", "--config-dir", str(config_dir))
    assert code == 2
    assert "unknown group 'GHOST'" in out
    assert "Result: NOT READY" in out


# ------------------------------------------------------------------ A2: blocklists commands

from tests.blocklist_fixtures import ScriptedFetcher, adblock_list, domains, ok  # noqa: E402

_A_URL = "https://cdn.example/a.txt"
_B_URL = "https://cdn.example/b.txt"


def _lists_fetcher(count: int = 40) -> ScriptedFetcher:
    return ScriptedFetcher(
        {
            _A_URL: ok(_A_URL, adblock_list(domains(count), last_modified=FIXED_NOW)),
            _B_URL: ok(_B_URL, "\n".join(domains(count, "mal")) + "\n" + "# pad " * 300 + "\n"),
        }
    )


def _bl(
    config_dir: Path, *argv: str, fetcher: ScriptedFetcher | None = None
) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(
        ["blocklists", *argv, "--config-dir", str(config_dir)],
        out=out,
        err=err,
        now=lambda: FIXED_NOW,
        fetcher=fetcher or _lists_fetcher(),
    )
    return code, out.getvalue(), err.getvalue()


def test_blocklists_update_is_dry_run_by_default(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    code, out, _ = _bl(config_dir, "update")
    assert code == 0
    assert "list-a: would_activate (dry-run)" in out
    assert "list-b: would_activate (dry-run)" in out
    assert not (config_dir.parent / ".local").exists()


def test_blocklists_apply_status_and_rollback(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    assert _bl(config_dir, "update", "--apply")[0] == 0
    code, out, _ = _bl(config_dir, "status")
    assert code == 0 and "list-a: current=" in out and "entries=40" in out
    assert "backup=-" in out

    code, _, err = _bl(config_dir, "rollback", "list-a", "--apply")
    assert code == 1 and "no previous" in err

    assert _bl(config_dir, "update", "--apply", fetcher=_lists_fetcher(45))[0] == 0
    code, out, _ = _bl(config_dir, "rollback", "list-a")
    assert code == 0 and "dry-run: would roll back" in out
    code, out, _ = _bl(config_dir, "rollback", "list-a", "--apply")
    assert code == 0 and "rolled back" in out
    assert "entries=40" in _bl(config_dir, "status")[1]


def test_blocklists_update_single_source_and_json(make_config_dir: MakeConfigDir) -> None:
    fetcher = _lists_fetcher()
    code, out, _ = _bl(
        make_config_dir(DEV_PROFILE),
        "update",
        "--source",
        "list-a",
        "--format",
        "json",
        fetcher=fetcher,
    )
    payload = json.loads(out)
    assert code == 0
    assert [r["source_id"] for r in payload] == ["list-a"]
    assert fetcher.calls == [_A_URL]


def test_blocklists_unknown_source_exits_2(make_config_dir: MakeConfigDir) -> None:
    code, _, err = _bl(make_config_dir(DEV_PROFILE), "update", "--source", "nope")
    assert code == 2 and "unknown source" in err


def test_blocklists_failed_update_exits_1(make_config_dir: MakeConfigDir) -> None:
    code, out, _ = _bl(make_config_dir(DEV_PROFILE), "update", fetcher=ScriptedFetcher({}))
    assert code == 1 and "kept_previous" in out and "blocklist_update_failure" in out


def test_blocklists_refused_in_production(repo_config_dir: Path) -> None:
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(
        [
            "blocklists",
            "update",
            "--env",
            "production",
            "--profile",
            str(repo_config_dir / "app" / "production.example.yaml"),
        ],
        out=out,
        err=err,
    )
    assert code == 1 and "development-only" in err.getvalue()


def test_blocklists_config_problems(make_config_dir: MakeConfigDir, tmp_path: Path) -> None:
    code, _, err = _bl(tmp_path / "missing", "update")
    assert code == 2 and "configuration error" in err

    bad = _EXPIRING_ALLOW.replace("[SMART-TV]", "[GHOST]")
    code, _, err = _bl(make_config_dir(DEV_PROFILE, **{"rules__allow.yaml": bad}), "status")
    assert code == 2 and "filtering configuration has errors" in err


def test_blocklists_unresolved_data_dir(make_config_dir: MakeConfigDir) -> None:
    text = DEV_PROFILE.replace("data_dir: .local/data", 'data_dir: "<<AUDIT:paths.data_dir>>"')
    code, _, err = _bl(make_config_dir(text), "status")
    assert code == 1 and "unresolved" in err


# ------------------------------------------------------------------ A3: policy explain


def _explain(config_dir: Path | None, *argv: str) -> tuple[int, str, str]:
    base = ["policy", "explain", *argv]
    if config_dir is not None:
        base += ["--config-dir", str(config_dir)]
    out, err = io.StringIO(), io.StringIO()
    return cli.main(base, out=out, err=err, now=lambda: FIXED_NOW), out.getvalue(), err.getvalue()


def test_policy_explain_repository_config_protected_domain() -> None:
    code, out, _ = _explain(None, "--group", "SMART-TV", "rr1---sn-x.googlevideo.com")
    assert code == 0
    assert "group SMART-TV uses: hagezi-light, hagezi-tif-mini" in out
    assert "allowed (protected)" in out


def test_policy_explain_uses_active_artifacts(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    assert _bl(config_dir, "update", "--apply")[0] == 0
    code, out, _ = _explain(
        config_dir,
        "--group",
        "DEFAULT",
        "ads3.blocked.example",
        "mal3.blocked.example",
        "sub.googlevideo.example",
        "--format",
        "json",
    )
    payload = json.loads(out)
    assert (
        code == 0 and payload["policy_sources"] == ["list-a", "list-b"] and payload["notes"] == []
    )
    verdicts = {d["domain"]: (d["verdict"], d["reason"]) for d in payload["decisions"]}
    assert verdicts["ads3.blocked.example"] == ("blocked", "blocklist")
    assert verdicts["mal3.blocked.example"] == ("blocked", "blocklist")
    assert verdicts["sub.googlevideo.example"] == ("allowed", "protected")

    code, out, _ = _explain(config_dir, "--group", "SMART-TV", "ads3.blocked.example")
    assert code == 0 and "allowed (default)" in out  # list-a is not in the conservative policy


def test_policy_explain_notes_missing_artifacts(make_config_dir: MakeConfigDir) -> None:
    code, out, _ = _explain(make_config_dir(DEV_PROFILE), "--group", "DEFAULT", "a.example")
    assert code == 0 and "no active artifact" in out


def test_policy_explain_invalid_input_and_config(
    make_config_dir: MakeConfigDir, tmp_path: Path
) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    assert _explain(config_dir, "--group", "GUEST", "a.example")[0] == 2
    assert _explain(config_dir, "--group", "DEFAULT", "*.example")[0] == 2
    assert _explain(tmp_path / "missing", "--group", "DEFAULT", "a.example")[0] == 2
    bad = _EXPIRING_ALLOW.replace("[SMART-TV]", "[GHOST]")
    assert (
        _explain(
            make_config_dir(DEV_PROFILE, **{"rules__allow.yaml": bad}),
            "--group",
            "DEFAULT",
            "a.example",
        )[0]
        == 2
    )


def test_policy_explain_unresolved_data_dir_and_corrupt_artifact(
    make_config_dir: MakeConfigDir,
) -> None:
    text = DEV_PROFILE.replace("data_dir: .local/data", 'data_dir: "<<AUDIT:paths.data_dir>>"')
    code, out, _ = _explain(make_config_dir(text), "--group", "DEFAULT", "a.example")
    assert code == 0 and "unresolved" in out


def test_policy_explain_reports_unreadable_artifact(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    assert _bl(config_dir, "update", "--apply", "--source", "list-a")[0] == 0
    store = config_dir.parent / ".local" / "data" / "blocklists" / "list-a" / "artifacts"
    for artifact in store.glob("*.txt"):
        artifact.write_text("tampered\n")
    code, out, _ = _explain(config_dir, "--group", "DEFAULT", "a.example")
    assert code == 0 and "unreadable" in out


# ------------------------------------------------------------------ A4: storage commands

from home_dns.core.storage import DiskUsage as _DiskUsage  # noqa: E402


class _FakeDisk:
    """Injectable DiskUsageProvider for CLI tests: reports a fixed usage regardless of path."""

    def __init__(self, used_percent: float, total: int = 1_000_000) -> None:
        used = round(total * used_percent / 100)
        self._usage = _DiskUsage(total_bytes=total, used_bytes=used, free_bytes=total - used)

    def get(self, path: Path) -> _DiskUsage:
        return self._usage


def _storage(config_dir: Path, *argv: str, disk: _FakeDisk | None = None) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(
        ["storage", *argv, "--config-dir", str(config_dir)],
        out=out,
        err=err,
        now=lambda: FIXED_NOW,
        disk=disk or _FakeDisk(10),
    )
    return code, out.getvalue(), err.getvalue()


def test_storage_status_reports_disk_state_and_categories(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    code, out, _ = _storage(config_dir, "status", disk=_FakeDisk(85))
    assert code == 0
    assert "state=auto_cleanup" in out
    assert "category data" in out and "category logs" in out


def test_storage_status_json_matches_thresholds(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    code, out, _ = _storage(config_dir, "status", "--format", "json", disk=_FakeDisk(95))
    payload = json.loads(out)
    assert code == 0
    assert payload["state"] == "emergency"
    assert payload["disk"]["used_bytes"] > 0


def test_storage_status_shows_artifact_counts_after_update(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    assert _bl(config_dir, "update", "--apply")[0] == 0
    code, out, _ = _storage(config_dir, "status")
    assert code == 0
    assert "blocklist artifacts" in out and "list-a=1" in out


def test_storage_cleanup_is_dry_run_by_default(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    tmp_dir = config_dir.parent / ".local" / "tmp"
    tmp_dir.mkdir(parents=True)
    old_file = tmp_dir / "old.tmp"
    old_file.write_bytes(b"x")
    old_ts = (FIXED_NOW - timedelta(hours=48)).timestamp()
    __import__("os").utime(old_file, (old_ts, old_ts))

    code, out, _ = _storage(config_dir, "cleanup", disk=_FakeDisk(85))
    assert code == 0 and "(dry-run)" in out and "removed: old.tmp" in out
    assert old_file.exists()


def test_storage_cleanup_apply_removes_old_temp_files(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    tmp_dir = config_dir.parent / ".local" / "tmp"
    tmp_dir.mkdir(parents=True)
    old_file = tmp_dir / "old.tmp"
    old_file.write_bytes(b"x")
    old_ts = (FIXED_NOW - timedelta(hours=48)).timestamp()
    __import__("os").utime(old_file, (old_ts, old_ts))

    code, out, _ = _storage(config_dir, "cleanup", "--apply", disk=_FakeDisk(85))
    assert code == 0 and "(dry-run)" not in out
    assert not old_file.exists()


def test_storage_cleanup_healthy_state_does_nothing(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    code, out, _ = _storage(config_dir, "cleanup", "--apply", disk=_FakeDisk(10))
    assert code == 0 and "state=healthy action=none" in out


def test_storage_backup_and_restore_round_trip(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    original = (config_dir / "groups" / "groups.yaml").read_text()
    code, out, _ = _storage(config_dir, "backup", "--apply")
    assert code == 0 and "backup-" in out
    name = out.split(":")[0]

    # Corrupt a non-loaded file (not app/development.yaml, which _storage's own _load() needs
    # to succeed just to run the restore command).
    (config_dir / "groups" / "groups.yaml").write_text("tampered: true\n")
    code, out, _ = _storage(config_dir, "restore", name, "--apply")
    assert code == 0 and "file(s) restored" in out
    assert (config_dir / "groups" / "groups.yaml").read_text() == original


def test_storage_backup_dry_run_writes_nothing(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    backup_dir = config_dir.parent / ".local" / "backups"
    code, _, _ = _storage(config_dir, "backup")
    assert code == 0
    assert not backup_dir.exists()


def test_storage_restore_unknown_backup_is_refused(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    code, _, err = _storage(config_dir, "restore", "backup-20000101T000000Z", "--apply")
    assert code == 1 and "restore refused" in err


def test_storage_verify_ok_with_no_backups_or_artifacts(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    code, out, _ = _storage(config_dir, "verify")
    assert code == 0 and "verify: ok" in out


def test_storage_verify_detects_tampered_backup(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    _storage(config_dir, "backup", "--apply")
    backup_dir = config_dir.parent / ".local" / "backups"
    [backup] = list(backup_dir.iterdir())
    manifest = json.loads((backup / "manifest.json").read_text())
    entry = manifest["entries"][0]
    tampered_file = backup / entry["source"] / entry["path"]
    tampered_file.write_text("corrupted\n")

    code, out, _ = _storage(config_dir, "verify", "--format", "json")
    payload = json.loads(out)
    assert code == 1 and not payload["ok"]
    assert any("mismatch" in p for p in payload["problems"])


def test_storage_verify_detects_corrupted_artifact(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    assert _bl(config_dir, "update", "--apply")[0] == 0
    artifacts_dir = config_dir.parent / ".local" / "data" / "blocklists" / "list-a" / "artifacts"
    [artifact] = list(artifacts_dir.glob("*.txt"))
    artifact.write_text("tampered\n")

    code, out, _ = _storage(config_dir, "verify")
    assert code == 1 and "artifact list-a/current" in out


def test_storage_refused_in_production(repo_config_dir: Path) -> None:
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(
        [
            "storage",
            "status",
            "--env",
            "production",
            "--profile",
            str(repo_config_dir / "app" / "production.example.yaml"),
        ],
        out=out,
        err=err,
    )
    assert code == 1 and "development-only" in err.getvalue()


def test_storage_unresolved_tmp_dir_is_refused(make_config_dir: MakeConfigDir) -> None:
    text = DEV_PROFILE.replace("tmp_dir: .local/tmp", 'tmp_dir: "<<AUDIT:paths.tmp_dir>>"')
    config_dir = make_config_dir(text)
    code, _, err = _storage(config_dir, "status")
    assert code == 1 and "unresolved" in err


def test_storage_config_load_error_exits_2(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE, **{"storage__storage.yaml": "schema_version: 2\n"})
    code, _, err = _storage(config_dir, "status")
    assert code == 2 and "configuration error" in err


# ------------------------------------------------------- A4.1 (RAM/tmpfs audit): tmp_dir health


def test_storage_status_reports_missing_tmp_dir(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    tmp_dir = config_dir.parent / ".local" / "tmp"
    assert not tmp_dir.exists()  # never created by validate-config or other setup
    code, out, _ = _storage(config_dir, "status")
    assert code == 0
    assert "tmp_dir is missing or not writable" in out


def test_storage_status_json_reports_tmp_dir_usable(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    (config_dir.parent / ".local" / "tmp").mkdir(parents=True)
    code, out, _ = _storage(config_dir, "status", "--format", "json")
    payload = json.loads(out)
    assert code == 0 and payload["tmp_dir_usable"] is True


def test_storage_status_never_creates_tmp_dir(make_config_dir: MakeConfigDir) -> None:
    """Regression: reading status must stay read-only (no probe side effects)."""
    config_dir = make_config_dir(DEV_PROFILE)
    _storage(config_dir, "status")
    assert not (config_dir.parent / ".local" / "tmp").exists()


def test_backup_cleans_up_snapshot_directory_even_when_create_backup_fails(
    make_config_dir: MakeConfigDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Audit fix: a failed create_backup() must not leave the DB-snapshot staging dir behind."""
    config_dir = make_config_dir(DEV_PROFILE)
    data_dir = config_dir.parent / ".local" / "data"
    data_dir.mkdir(parents=True)
    db_path = data_dir / "home-dns.db"
    connection = sqlite3.connect(db_path)
    connection.execute("CREATE TABLE t (id INTEGER)")
    connection.close()

    def explode(*args: object, **kwargs: object) -> None:
        raise cli.BackupError("simulated: name collision")

    monkeypatch.setattr(cli, "create_backup", explode)
    out, err = io.StringIO(), io.StringIO()
    with pytest.raises(cli.BackupError):
        cli.main(
            ["storage", "backup", "--apply", "--config-dir", str(config_dir)],
            out=out,
            err=err,
            now=lambda: FIXED_NOW,
        )
    tmp_dir = config_dir.parent / ".local" / "tmp"
    leftovers = list(tmp_dir.glob(".db-snapshot-*")) if tmp_dir.exists() else []
    assert leftovers == []


# ---------------------------------------------------------------------- A5: monitoring commands


def _mon(config_dir: Path, *argv: str, disk: _FakeDisk | None = None) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(
        ["monitoring", *argv, "--config-dir", str(config_dir)],
        out=out,
        err=err,
        now=lambda: FIXED_NOW,
        disk=disk or _FakeDisk(10),
    )
    return code, out.getvalue(), err.getvalue()


def test_monitoring_status_healthy_storage_is_ok_no_alert(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    code, out, _ = _mon(config_dir, "status", disk=_FakeDisk(10))
    assert code == 0
    assert "check=ok incident=ok transition=none" in out
    assert "alert" not in out


def test_monitoring_status_dry_run_does_not_persist(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    code, out, _ = _mon(config_dir, "status", disk=_FakeDisk(95))
    assert code == 0 and "(dry-run: not persisted)" in out
    assert not (config_dir.parent / ".local" / "data" / "monitoring").exists()


def test_monitoring_status_apply_opens_incident_after_two_bad_checks(
    make_config_dir: MakeConfigDir,
) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    code, out, _ = _mon(config_dir, "status", "--apply", disk=_FakeDisk(95))
    assert code == 0 and "incident=suspect" in out and "alert" not in out

    code, out, _ = _mon(config_dir, "status", "--apply", disk=_FakeDisk(95))
    assert code == 0 and "incident=incident transition=opened" in out
    assert "alert [critical] storage_above_90" in out


def test_monitoring_status_recovers_after_incident(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    assert _mon(config_dir, "status", "--apply", disk=_FakeDisk(95))[0] == 0
    assert "opened" in _mon(config_dir, "status", "--apply", disk=_FakeDisk(95))[1]

    code, out, _ = _mon(config_dir, "status", "--apply", disk=_FakeDisk(10))
    assert code == 0 and "transition=recovered" in out
    assert "alert [info] service_recovered" in out


def test_monitoring_status_json_format(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    code, out, _ = _mon(config_dir, "status", "--format", "json", disk=_FakeDisk(95))
    payload = json.loads(out)
    assert code == 0
    assert payload["check"] == "storage"
    assert payload["status"] == "problem"
    assert payload["transition"] == "none"  # first bad check: SUSPECT, no alert yet


def test_monitoring_refused_in_production(repo_config_dir: Path) -> None:
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(
        [
            "monitoring",
            "status",
            "--env",
            "production",
            "--profile",
            str(repo_config_dir / "app" / "production.example.yaml"),
        ],
        out=out,
        err=err,
    )
    assert code == 1 and "development-only" in err.getvalue()


def test_monitoring_config_load_error_exits_2(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(
        DEV_PROFILE, **{"monitoring__monitoring.yaml": "schema_version: 2\n"}
    )
    code, _, err = _mon(config_dir, "status")
    assert code == 2 and "configuration error" in err


def test_monitoring_unresolved_tmp_dir_is_refused(make_config_dir: MakeConfigDir) -> None:
    text = DEV_PROFILE.replace("tmp_dir: .local/tmp", 'tmp_dir: "<<AUDIT:paths.tmp_dir>>"')
    code, _, err = _mon(make_config_dir(text), "status")
    assert code == 1 and "unresolved" in err


def test_storage_alert_helper_covers_every_transition() -> None:
    from home_dns.core.storage import StorageReport as _Report
    from home_dns.core.storage import ThresholdState as _State

    def report(state: _State) -> _Report:
        return _Report(
            checked_at=FIXED_NOW,
            disk=_DiskUsage(total_bytes=100, used_bytes=50, free_bytes=50),
            state=state,
        )

    assert cli._storage_alert(report(_State.HEALTHY), cli.TransitionKind.NONE) is None
    healthy_opened = cli._storage_alert(report(_State.HEALTHY), cli.TransitionKind.OPENED)
    assert healthy_opened is None  # defensive: HEALTHY has no event, so OPENED can't reach here

    warning = cli._storage_alert(report(_State.WARNING), cli.TransitionKind.OPENED)
    assert warning is not None and warning.severity == "warning"

    critical = cli._storage_alert(report(_State.EMERGENCY), cli.TransitionKind.REMINDER)
    assert critical is not None and critical.severity == "critical"

    recovered = cli._storage_alert(report(_State.HEALTHY), cli.TransitionKind.RECOVERED)
    assert recovered is not None and recovered.event == "service_recovered"


def test_blocklists_update_escalates_after_three_consecutive_kept_previous(
    make_config_dir: MakeConfigDir,
) -> None:
    """Owner-approved ladder (2026-09-13): warning, warning, critical, then reset on success."""
    config_dir = make_config_dir(DEV_PROFILE)
    empty = ScriptedFetcher({})

    code, out, _ = _bl(config_dir, "update", "--apply", "--source", "list-a", fetcher=empty)
    assert code == 1 and "kept_previous" in out and "[critical]" not in out

    code, out, _ = _bl(config_dir, "update", "--apply", "--source", "list-a", fetcher=empty)
    assert code == 1 and "kept_previous" in out and "[critical]" not in out

    code, out, _ = _bl(config_dir, "update", "--apply", "--source", "list-a", fetcher=empty)
    assert code == 1 and "kept_previous" in out
    assert "alert [critical] failed_update: list-a: 3 consecutive" in out

    code, out, _ = _bl(config_dir, "update", "--apply", "--source", "list-a")
    assert code == 0 and "activated" in out and "[critical] failed_update" not in out

    code, out, _ = _bl(config_dir, "update", "--apply", "--source", "list-a", fetcher=empty)
    assert code == 1 and "[critical] failed_update" not in out  # counter reset, back to 1st


# --------------------------------------------------------------------------- A6: notify commands


def _notify_cmd(config_dir: Path, *argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(
        ["notify", *argv, "--config-dir", str(config_dir)], out=out, err=err, now=lambda: FIXED_NOW
    )
    return code, out.getvalue(), err.getvalue()


def test_notify_test_is_dry_run_by_default(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    code, out, _ = _notify_cmd(config_dir, "test")
    assert code == 0
    assert "sent=False" in out and "(dry-run)" in out


def test_notify_test_apply_sends_via_default_mock_notifier(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    code, out, _ = _notify_cmd(config_dir, "test", "--apply")
    assert code == 0
    assert "mock: sent=True" in out
    assert "(dry-run)" not in out


def test_notify_test_apply_dry_run_does_not_persist_anti_spam_state(
    make_config_dir: MakeConfigDir,
) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    _notify_cmd(config_dir, "test")
    assert not (config_dir.parent / ".local" / "data" / "notify").exists()


def test_notify_test_second_apply_within_cooldown_is_suppressed(
    make_config_dir: MakeConfigDir,
) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    code, out, _ = _notify_cmd(config_dir, "test", "--apply")
    assert code == 0 and "mock: sent=True" in out

    code, out, _ = _notify_cmd(config_dir, "test", "--apply")
    assert code == 0 and "suppressed by anti-spam policy" in out


def test_notify_refused_in_production(repo_config_dir: Path) -> None:
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(
        [
            "notify",
            "test",
            "--env",
            "production",
            "--profile",
            str(repo_config_dir / "app" / "production.example.yaml"),
        ],
        out=out,
        err=err,
    )
    assert code == 1 and "development-only" in err.getvalue()


def test_notify_config_load_error_exits_2(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE, **{"telegram__alerts.yaml": "schema_version: 2\n"})
    code, _, err = _notify_cmd(config_dir, "test")
    assert code == 2 and "configuration error" in err


def test_notify_unresolved_data_dir_is_refused(make_config_dir: MakeConfigDir) -> None:
    text = DEV_PROFILE.replace("data_dir: .local/data", 'data_dir: "<<AUDIT:paths.data_dir>>"')
    code, _, err = _notify_cmd(make_config_dir(text), "test")
    assert code == 1 and "unresolved" in err


def test_notify_telegram_kind_without_secrets_is_refused(make_config_dir: MakeConfigDir) -> None:
    text = DEV_PROFILE.replace("dns_provider:", "notifier:\n  kind: telegram\ndns_provider:")
    code, _, err = _notify_cmd(make_config_dir(text), "test", "--apply")
    assert code == 1 and "TELEGRAM_BOT_TOKEN" in err


def test_notify_telegram_kind_with_secrets_builds_a_telegram_notifier(
    make_config_dir: MakeConfigDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "abc123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    text = DEV_PROFILE.replace("dns_provider:", "notifier:\n  kind: telegram\ndns_provider:")
    config_dir = make_config_dir(text)
    config, _ = cli._load(argparse.Namespace(env=None, config_dir=config_dir, profile=None))
    notifier = cli._build_notifier(
        config, config_dir.parent / ".local" / "data", now=lambda: FIXED_NOW
    )
    assert notifier.name == "telegram"
    assert "abc123" not in repr(notifier)
