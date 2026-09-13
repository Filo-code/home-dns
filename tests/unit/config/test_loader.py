from collections.abc import Callable
from pathlib import Path

import pytest

from home_dns.config.loader import (
    ConfigLoadError,
    default_config_dir,
    load_config,
    resolve_environment,
    scan_config_tree,
)
from home_dns.config.placeholders import Placeholder
from home_dns.config.settings import Environment, ProviderKind
from tests.conftest import DEV_PROFILE, PROD_READY_PROFILE

MakeConfigDir = Callable[..., Path]


def test_loads_committed_development_profile(repo_config_dir: Path) -> None:
    loaded = load_config(environment=Environment.DEVELOPMENT, config_dir=repo_config_dir)
    assert loaded.settings.dns_provider.kind is ProviderKind.MOCK
    assert loaded.project_root == repo_config_dir.parent


def test_loads_committed_production_example_with_placeholders(repo_config_dir: Path) -> None:
    loaded = load_config(
        environment=Environment.PRODUCTION,
        config_dir=repo_config_dir,
        profile=repo_config_dir / "app" / "production.example.yaml",
    )
    assert isinstance(loaded.settings.paths.data_dir, Placeholder)
    assert isinstance(loaded.settings.api.port, Placeholder)


def test_missing_profile_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigLoadError, match="file not found"):
        load_config(environment=Environment.DEVELOPMENT, config_dir=tmp_path)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("environment: [unclosed", "invalid YAML"),
        ("- just\n- a list\n", "top level must be a mapping"),
        (DEV_PROFILE.replace("environment: development\n", ""), "declares environment None"),
        (DEV_PROFILE + "unexpected: 1\n", "unexpected"),
        (DEV_PROFILE.replace("port: 8080", "port: 70000"), "api.port"),
        (DEV_PROFILE.replace("kind: mock", "kind: pihole_v6"), "pihole_v6 is required"),
        (DEV_PROFILE.replace("data_dir: .local/data", "data_dir: <<AUDT:x>>"), "malformed"),
    ],
)
def test_invalid_profiles_are_rejected(
    make_config_dir: MakeConfigDir, text: str, message: str
) -> None:
    config_dir = make_config_dir(text)
    with pytest.raises(ConfigLoadError, match=message):
        load_config(environment=Environment.DEVELOPMENT, config_dir=config_dir)


def test_empty_profile_is_rejected_as_environment_mismatch(make_config_dir: MakeConfigDir) -> None:
    with pytest.raises(ConfigLoadError, match="declares environment None"):
        load_config(environment=Environment.DEVELOPMENT, config_dir=make_config_dir(""))


def test_development_profile_cannot_start_as_production(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE, env="production")
    with pytest.raises(ConfigLoadError, match="'development' but 'production'"):
        load_config(environment=Environment.PRODUCTION, config_dir=config_dir)


@pytest.mark.parametrize("key", ["password", "api_key", "bot_token", "clientSecret", "private-key"])
def test_secret_like_keys_are_rejected(make_config_dir: MakeConfigDir, key: str) -> None:
    text = DEV_PROFILE.replace("    seed: 7", f"    seed: 7\n    {key}: hunter2")
    with pytest.raises(ConfigLoadError, match="secret-like keys"):
        load_config(environment=Environment.DEVELOPMENT, config_dir=make_config_dir(text))


def test_secret_value_is_not_echoed_in_errors(make_config_dir: MakeConfigDir) -> None:
    text = DEV_PROFILE.replace("    seed: 7", "    seed: 7\n    password: do-not-print-me")
    with pytest.raises(ConfigLoadError) as excinfo:
        load_config(environment=Environment.DEVELOPMENT, config_dir=make_config_dir(text))
    assert "do-not-print-me" not in str(excinfo.value)


def test_environment_variables_override_profile(
    make_config_dir: MakeConfigDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME_DNS_API__PORT", "9090")
    monkeypatch.setenv("HOME_DNS_DNS_PROVIDER__MOCK__SEED", "99")
    loaded = load_config(
        environment=Environment.DEVELOPMENT, config_dir=make_config_dir(DEV_PROFILE)
    )
    assert loaded.settings.api.port == 9090
    assert loaded.settings.dns_provider.mock.seed == 99
    assert loaded.settings.api.bind_host.__str__() == "127.0.0.1"


def test_environment_variable_can_resolve_a_placeholder(
    make_config_dir: MakeConfigDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    text = PROD_READY_PROFILE.replace("port: 8080", 'port: "<<REQUIRED:api.port>>"')
    monkeypatch.setenv("HOME_DNS_API__PORT", "8443")
    loaded = load_config(
        environment=Environment.PRODUCTION, config_dir=make_config_dir(text, env="production")
    )
    assert loaded.settings.api.port == 8443


def test_invalid_environment_override_is_a_load_error(
    make_config_dir: MakeConfigDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME_DNS_API__PORT", "not-a-port")
    with pytest.raises(ConfigLoadError, match=r"api\.port"):
        load_config(environment=Environment.DEVELOPMENT, config_dir=make_config_dir(DEV_PROFILE))


def test_secrets_come_from_environment_and_are_redacted(
    make_config_dir: MakeConfigDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME_DNS_PIHOLE_APP_PASSWORD", "s3cr3t-value")
    loaded = load_config(
        environment=Environment.DEVELOPMENT, config_dir=make_config_dir(DEV_PROFILE)
    )
    assert loaded.secrets.pihole_app_password is not None
    assert loaded.secrets.pihole_app_password.get_secret_value() == "s3cr3t-value"
    assert "s3cr3t-value" not in repr(loaded.secrets)


def test_resolve_relative_and_absolute_paths(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(DEV_PROFILE)
    loaded = load_config(environment=Environment.DEVELOPMENT, config_dir=config_dir)
    assert loaded.resolve(Path(".local/data")) == config_dir.resolve().parent / ".local/data"
    assert loaded.resolve(Path("/srv/x")) == Path("/srv/x")


def test_resolve_environment() -> None:
    assert resolve_environment(None, {}) is Environment.DEVELOPMENT
    assert resolve_environment(None, {"HOME_DNS_ENV": "production"}) is Environment.PRODUCTION
    assert (
        resolve_environment("development", {"HOME_DNS_ENV": "production"})
        is Environment.DEVELOPMENT
    )
    with pytest.raises(ConfigLoadError, match="unknown environment"):
        resolve_environment("staging", {})


def test_default_config_dir(tmp_path: Path, repo_config_dir: Path) -> None:
    assert default_config_dir({}) == repo_config_dir
    assert default_config_dir({"HOME_DNS_CONFIG_DIR": str(tmp_path)}) == tmp_path


def test_scan_config_tree_on_repository_config(repo_config_dir: Path) -> None:
    results = scan_config_tree(repo_config_dir)
    assert results, "expected domain config files to be scanned"
    assert all(r.error is None for r in results)
    assert all("app" not in r.path.relative_to(repo_config_dir).parts[:1] for r in results)


def test_scan_config_tree_reports_problems(make_config_dir: MakeConfigDir) -> None:
    config_dir = make_config_dir(
        DEV_PROFILE,
        **{
            "groups__groups.yaml": (
                "groups:\n  - name: DEFAULT\n    note: '<<AUDIT:groups.note>>'\n"
            ),
            "telegram__alerts.yaml": "bot_token: nope\n",
            "policies__broken.yml": "a: [\n",
            "storage__bad.yaml": "value: '<<WRONG>>'\n",
        },
    )
    by_name = {r.path.name: r for r in scan_config_tree(config_dir)}
    assert by_name["groups.yaml"].placeholders == ("groups[0].note=<<AUDIT:groups.note>>",)
    assert by_name["alerts.yaml"].error and "secret-like" in by_name["alerts.yaml"].error
    assert by_name["broken.yml"].error and "invalid YAML" in by_name["broken.yml"].error
    assert by_name["bad.yaml"].error and "malformed" in by_name["bad.yaml"].error
