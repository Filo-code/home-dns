from datetime import UTC, datetime
from pathlib import Path

import pytest

from home_dns.core.notify import AntiSpamState
from home_dns.storage.notify import NotifyStore, NotifyStoreError

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)


def test_load_defaults_to_empty_state_when_no_file_exists(tmp_path: Path) -> None:
    assert NotifyStore(tmp_path).load() == AntiSpamState()


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    store = NotifyStore(tmp_path)
    state = AntiSpamState(last_sent_at={"k": NOW}, sent_within_hour=(NOW,))
    store.save(state, dry_run=False)
    assert store.load() == state


def test_save_dry_run_does_not_write(tmp_path: Path) -> None:
    store = NotifyStore(tmp_path)
    store.save(AntiSpamState(last_sent_at={"k": NOW}), dry_run=True)
    assert store.load() == AntiSpamState()
    assert not (tmp_path / "anti_spam.json").exists()


def test_load_corrupted_file_raises(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "anti_spam.json").write_text("not json", encoding="utf-8")
    with pytest.raises(NotifyStoreError):
        NotifyStore(tmp_path).load()
