import httpx
import pytest

from home_dns.core.monitoring import BackoffPolicy
from home_dns.notify.base import OutgoingMessage
from home_dns.notify.telegram import TelegramNotifier

MESSAGE = OutgoingMessage("critical", "dns_down", "DNS is down")


def _client(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler)


def _notifier(
    handler: httpx.MockTransport, *, backoff: BackoffPolicy | None = None
) -> tuple[TelegramNotifier, list[float]]:
    sleeps: list[float] = []
    notifier = TelegramNotifier(
        bot_token="real-secret-token",
        chat_id="12345",
        client=_client(handler),
        backoff=backoff
        or BackoffPolicy(max_attempts=3, base_delay_seconds=0.01, max_delay_seconds=0.02),
        sleep=sleeps.append,
    )
    return notifier, sleeps


def test_dry_run_never_calls_the_api() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    notifier, _ = _notifier(httpx.MockTransport(handler))
    result = notifier.send(MESSAGE, dry_run=True)
    assert not result.sent
    assert calls == []


def test_success_on_first_attempt() -> None:
    notifier, sleeps = _notifier(httpx.MockTransport(lambda r: httpx.Response(200)))
    result = notifier.send(MESSAGE, dry_run=False)
    assert result.sent
    assert sleeps == []


def test_posts_chat_id_and_text_to_the_bot_endpoint() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content
        return httpx.Response(200)

    notifier, _ = _notifier(httpx.MockTransport(handler))
    notifier.send(MESSAGE, dry_run=False)
    assert "real-secret-token" in seen["url"]
    assert b"12345" in seen["body"]
    assert b"DNS is down" in seen["body"]


def test_4xx_is_not_retried() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(401)

    notifier, sleeps = _notifier(httpx.MockTransport(handler))
    result = notifier.send(MESSAGE, dry_run=False)
    assert not result.sent
    assert "401" in result.detail
    assert len(calls) == 1
    assert sleeps == []


def test_5xx_retries_with_backoff_then_gives_up() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(503)

    notifier, sleeps = _notifier(
        httpx.MockTransport(handler),
        backoff=BackoffPolicy(max_attempts=3, base_delay_seconds=0.01, max_delay_seconds=0.02),
    )
    result = notifier.send(MESSAGE, dry_run=False)
    assert not result.sent
    assert "retry budget exhausted" in result.detail
    assert len(calls) == 3
    assert sleeps == [0.01, 0.02]


def test_transport_error_retries_then_gives_up_without_raising() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    notifier, sleeps = _notifier(
        httpx.MockTransport(handler),
        backoff=BackoffPolicy(max_attempts=2, base_delay_seconds=0.01, max_delay_seconds=0.02),
    )
    result = notifier.send(MESSAGE, dry_run=False)
    assert not result.sent
    assert len(sleeps) == 1


def test_recovers_on_a_later_attempt() -> None:
    responses = iter([httpx.Response(503), httpx.Response(200)])

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    notifier, sleeps = _notifier(
        httpx.MockTransport(handler),
        backoff=BackoffPolicy(max_attempts=3, base_delay_seconds=0.01, max_delay_seconds=0.02),
    )
    result = notifier.send(MESSAGE, dry_run=False)
    assert result.sent
    assert len(sleeps) == 1


@pytest.mark.parametrize("view", ["repr"])
def test_token_is_redacted_from_repr(view: str) -> None:
    notifier, _ = _notifier(httpx.MockTransport(lambda r: httpx.Response(200)))
    assert "real-secret-token" not in repr(notifier)
    assert "redacted" in repr(notifier)


def test_name_is_telegram() -> None:
    notifier, _ = _notifier(httpx.MockTransport(lambda r: httpx.Response(200)))
    assert notifier.name == "telegram"
