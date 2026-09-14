from home_dns.notify.base import OutgoingMessage
from home_dns.notify.mock import MockNotifier


def test_dry_run_does_not_record() -> None:
    notifier = MockNotifier()
    result = notifier.send(OutgoingMessage("info", "e", "t"), dry_run=True)
    assert not result.sent
    assert notifier.sent == []


def test_apply_records_the_message() -> None:
    notifier = MockNotifier()
    message = OutgoingMessage("critical", "dns_down", "DNS is down")
    result = notifier.send(message, dry_run=False)
    assert result.sent
    assert notifier.sent == [message]


def test_name_is_mock() -> None:
    assert MockNotifier().name == "mock"
