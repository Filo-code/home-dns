from pathlib import Path

import pytest

from home_dns.config.secrets_file import (
    SecretFileFormatError,
    SecretFilePermissionError,
    load_env_file,
)


def _write(path: Path, text: str, mode: int) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)


def test_loads_a_well_formed_owner_only_file(tmp_path: Path) -> None:
    path = tmp_path / "telegram.env"
    _write(path, "TELEGRAM_BOT_TOKEN=abc123\nTELEGRAM_CHAT_ID=999\n", 0o600)
    assert load_env_file(path) == {"TELEGRAM_BOT_TOKEN": "abc123", "TELEGRAM_CHAT_ID": "999"}


def test_ignores_blank_lines_and_comments(tmp_path: Path) -> None:
    path = tmp_path / "telegram.env"
    _write(path, "\n# a comment\nTELEGRAM_BOT_TOKEN=abc123\n\n", 0o600)
    assert load_env_file(path) == {"TELEGRAM_BOT_TOKEN": "abc123"}


def test_strips_surrounding_quotes(tmp_path: Path) -> None:
    path = tmp_path / "telegram.env"
    _write(path, 'TELEGRAM_BOT_TOKEN="abc123"\n', 0o600)
    assert load_env_file(path) == {"TELEGRAM_BOT_TOKEN": "abc123"}


@pytest.mark.parametrize("mode", [0o640, 0o644, 0o604, 0o606])
def test_refuses_group_or_other_readable_file_before_reading_it(tmp_path: Path, mode: int) -> None:
    path = tmp_path / "telegram.env"
    _write(path, "TELEGRAM_BOT_TOKEN=super-secret-value\n", mode)
    with pytest.raises(SecretFilePermissionError):
        load_env_file(path)


def test_permission_error_message_never_contains_the_secret_value(tmp_path: Path) -> None:
    path = tmp_path / "telegram.env"
    _write(path, "TELEGRAM_BOT_TOKEN=super-secret-value\n", 0o644)
    with pytest.raises(SecretFilePermissionError) as excinfo:
        load_env_file(path)
    assert "super-secret-value" not in str(excinfo.value)


def test_owner_only_no_group_no_other_is_accepted(tmp_path: Path) -> None:
    path = tmp_path / "telegram.env"
    _write(path, "TELEGRAM_BOT_TOKEN=abc123\n", 0o700)
    assert load_env_file(path) == {"TELEGRAM_BOT_TOKEN": "abc123"}


def test_malformed_line_raises_format_error(tmp_path: Path) -> None:
    path = tmp_path / "telegram.env"
    _write(path, "not a key value line\n", 0o600)
    with pytest.raises(SecretFileFormatError, match="not a KEY=VALUE line"):
        load_env_file(path)


def test_empty_key_raises_format_error(tmp_path: Path) -> None:
    path = tmp_path / "telegram.env"
    _write(path, "=value\n", 0o600)
    with pytest.raises(SecretFileFormatError, match="empty key"):
        load_env_file(path)
