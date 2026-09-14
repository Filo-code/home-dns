import json
from datetime import UTC, datetime
from pathlib import Path

from home_dns.notify.base import OutgoingMessage
from home_dns.notify.file import FileNotifier

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "outbox.jsonl"
    notifier = FileNotifier(path, now=lambda: NOW)
    result = notifier.send(OutgoingMessage("info", "e", "t"), dry_run=True)
    assert not result.sent
    assert not path.exists()


def test_apply_appends_one_json_line(tmp_path: Path) -> None:
    path = tmp_path / "outbox.jsonl"
    notifier = FileNotifier(path, now=lambda: NOW)
    message = OutgoingMessage("critical", "dns_down", "DNS is down")
    result = notifier.send(message, dry_run=False)
    assert result.sent
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["severity"] == "critical"
    assert record["event"] == "dns_down"
    assert record["text"] == "DNS is down"
    assert record["sent_at"] == NOW.isoformat()


def test_apply_appends_across_multiple_sends(tmp_path: Path) -> None:
    path = tmp_path / "outbox.jsonl"
    notifier = FileNotifier(path, now=lambda: NOW)
    notifier.send(OutgoingMessage("info", "a", "1"), dry_run=False)
    notifier.send(OutgoingMessage("info", "b", "2"), dry_run=False)
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


def test_creates_parent_directory(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "dir" / "outbox.jsonl"
    notifier = FileNotifier(path, now=lambda: NOW)
    notifier.send(OutgoingMessage("info", "e", "t"), dry_run=False)
    assert path.exists()


def test_name_is_file() -> None:
    assert FileNotifier(Path("/tmp/x")).name == "file"
