import io
import json
from collections.abc import Callable
from datetime import UTC, datetime
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
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kw: calls.append(kw))
    code, _, _ = _run("serve", "--config-dir", str(make_config_dir(DEV_PROFILE)))
    assert code == 0
    assert calls == [{"host": "127.0.0.1", "port": 8080}]


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
    assert "sources=2" in out
    assert "no protected domains defined" in out


def test_repository_config_fails_strict_until_protected_domains_exist() -> None:
    assert _run("validate-config", "--strict")[0] == 1


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
