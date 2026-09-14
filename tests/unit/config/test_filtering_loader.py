from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from home_dns.config.filtering import filtering_config_files, load_filtering_config
from home_dns.config.loader import ConfigLoadError, scan_config_tree
from tests.conftest import DEV_PROFILE, FILTERING_FILES

MakeConfigDir = Callable[..., Path]
NOW = datetime(2026, 9, 13, tzinfo=UTC)


def test_repository_filtering_config_is_valid(repo_config_dir: Path) -> None:
    result = load_filtering_config(repo_config_dir, now=NOW)
    assert {g.id for g in result.config.groups} == {
        "DEFAULT",
        "PC",
        "GAMING",
        "MOBILE",
        "SMART-TV",
        "XBOX",
    }
    assert {s.id for s in result.config.sources} == {
        "hagezi-multi-pro",
        "hagezi-tif-mini",
        "hagezi-light",
        "hagezi-normal",
    }
    assert result.errors == ()
    assert result.warnings == ()
    assert len(result.config.protected_domains()) >= 250


def test_repository_sources_use_jsdelivr_primary_and_github_fallback(repo_config_dir: Path) -> None:
    for source in load_filtering_config(repo_config_dir, now=NOW).config.sources:
        assert source.urls.primary.host == "cdn.jsdelivr.net"
        assert source.urls.fallback is not None
        assert source.urls.fallback.host == "raw.githubusercontent.com"


def test_fixture_filtering_config_is_valid(make_config_dir: MakeConfigDir) -> None:
    result = load_filtering_config(make_config_dir(DEV_PROFILE), now=NOW)
    assert result.issues == ()
    assert result.evaluated_at == NOW


@pytest.mark.parametrize("missing", [k for k in FILTERING_FILES if not k.startswith("protected")])
def test_missing_filtering_file_is_a_load_error(
    make_config_dir: MakeConfigDir, missing: str
) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    (config_dir / missing.replace("__", "/")).unlink()
    with pytest.raises(ConfigLoadError, match="file not found"):
        load_filtering_config(config_dir, now=NOW)


def test_missing_protected_directory_is_a_load_error(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    (config_dir / "protected-domains" / "technology.yaml").unlink()
    (config_dir / "protected-domains").rmdir()
    with pytest.raises(ConfigLoadError, match="directory not found"):
        load_filtering_config(config_dir, now=NOW)


@pytest.mark.parametrize(
    ("file_key", "content", "message"),
    [
        ("groups__groups.yaml", "schema_version: 2\ngroups: []\n", "schema_version"),
        ("groups__groups.yaml", "groups: []\n", "schema_version"),
        (
            "groups__groups.yaml",
            "schema_version: 1\ngroups:\n  - {id: tv, description: x, policy: s}\n",
            r"groups\.0\.id",
        ),
        (
            "rules__allow.yaml",
            "schema_version: 1\nrules:\n  - domain: a.example\n",
            r"rules\.0\.reason",
        ),
        ("rules__deny.yaml", "schema_version: 1\nrules: []\nextra: 1\n", "extra"),
        (
            "blocklists__sources.yaml",
            "schema_version: 1\nsources:\n  - id: x\n    token: abc\n",
            "secret-like keys",
        ),
        (
            "rules__regex.yaml",
            "schema_version: 1\nrules:\n  - pattern: '<<TODO>>'\n",
            "malformed placeholder",
        ),
        (
            "protected-domains__technology.yaml",
            "schema_version: 1\ncategory: infra\ndescription: x\ndomains: []\n",
            "must match file name",
        ),
    ],
)
def test_schema_errors_name_the_file(
    make_config_dir: MakeConfigDir, file_key: str, content: str, message: str
) -> None:
    config_dir = make_config_dir(DEV_PROFILE, **{file_key: content})
    with pytest.raises(ConfigLoadError, match=message) as excinfo:
        load_filtering_config(config_dir, now=NOW)
    assert file_key.replace("__", "/") in str(excinfo.value)


def test_cross_reference_errors_are_returned_as_issues(make_config_dir: MakeConfigDir) -> None:
    deny = (
        "schema_version: 1\nrules:\n  - domain: www.googlevideo.example\n    reason: test rule\n"
        "    author: tests\n    created_at: 2026-09-01\n    groups: [DEFAULT]\n    source: t\n"
    )
    config_dir = make_config_dir(DEV_PROFILE, **{"rules__deny.yaml": deny})
    result = load_filtering_config(config_dir, now=NOW)
    assert [(e.location, e.message) for e in result.errors] == [
        ("deny[0]", "would block protected domain googlevideo.example")
    ]


def test_filtering_files_are_excluded_from_generic_scan(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE, storage=False, **{"telegram__alerts.yaml": "a: 1\n"})
    scanned = scan_config_tree(config_dir, exclude=filtering_config_files(config_dir))
    assert [s.path.name for s in scanned] == ["alerts.yaml"]


def test_repository_sources_have_approved_limits(repo_config_dir: Path) -> None:
    sources = {s.id: s for s in load_filtering_config(repo_config_dir, now=NOW).config.sources}
    multi, tif = sources["hagezi-multi-pro"], sources["hagezi-tif-mini"]
    assert (multi.update_interval_hours, multi.max_age_hours) == (24, 48)
    assert (tif.update_interval_hours, tif.max_age_hours) == (24, 48)
    assert multi.sanity is not None and tif.sanity is not None
    assert (multi.sanity.min_entries, multi.sanity.max_entries) == (180_000, 280_000)
    assert (multi.sanity.max_added_ratio, multi.sanity.max_removed_ratio) == (0.05, 0.05)
    assert (tif.sanity.min_entries, tif.sanity.max_entries) == (140_000, 225_000)
    assert (tif.sanity.max_added_ratio, tif.sanity.max_removed_ratio) == (0.12, 0.08)
