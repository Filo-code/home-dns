"""Telegram Bot API Notifier.

A transport or 5xx failure retries with backoff (reusing core.monitoring's restart-budget
primitives); a 4xx (bad token/chat id) does not retry. The budget exhausting never raises —
``send()`` returns ``sent=False`` instead, so a Telegram outage never crashes the caller.
The token is never logged, repr'd or included in any exception message.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx

from home_dns.core.monitoring import BackoffPolicy, RestartBudget, advance_restart_budget
from home_dns.notify.base import Notifier, NotifierError, OutgoingMessage, SendResult

API_BASE = "https://api.telegram.org"

# Short, synchronous retry — send() is called inline from a CLI/check invocation, not a
# background worker. Deliberately smaller than A5's check-restart budget, which spans
# separate scheduled process runs, not one blocking HTTP call.
DEFAULT_TELEGRAM_BACKOFF = BackoffPolicy(
    max_attempts=3, base_delay_seconds=1.0, max_delay_seconds=5.0, backoff_factor=2.0
)


class TelegramTransportError(NotifierError):
    """A transport-level failure (connection, timeout, TLS)."""


class TelegramNotifier(Notifier):
    def __init__(
        self,
        *,
        bot_token: str,
        chat_id: str,
        client: httpx.Client | None = None,
        backoff: BackoffPolicy = DEFAULT_TELEGRAM_BACKOFF,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._token = bot_token
        self._chat_id = chat_id
        self._client = client or httpx.Client(timeout=10.0)
        self._backoff = backoff
        self._sleep = sleep or time.sleep

    def __repr__(self) -> str:
        return f"TelegramNotifier(chat_id={self._chat_id!r}, bot_token=<redacted>)"

    @property
    def name(self) -> str:
        return "telegram"

    def send(self, message: OutgoingMessage, *, dry_run: bool = True) -> SendResult:
        if dry_run:
            return SendResult(sent=False, detail="dry-run: not sent")

        budget = RestartBudget()
        last_detail = "no attempt made"
        while True:
            try:
                response = self._client.post(
                    f"{API_BASE}/bot{self._token}/sendMessage",
                    json={"chat_id": self._chat_id, "text": message.text},
                )
            except httpx.HTTPError as exc:
                last_detail = f"transport error: {type(exc).__name__}"
            else:
                if response.status_code == 200:
                    return SendResult(sent=True, detail="delivered")
                if 400 <= response.status_code < 500:
                    return SendResult(sent=False, detail=f"rejected: HTTP {response.status_code}")
                last_detail = f"HTTP {response.status_code}"

            budget, delay = advance_restart_budget(budget, policy=self._backoff)
            if delay is None:
                return SendResult(sent=False, detail=f"retry budget exhausted: {last_detail}")
            self._sleep(delay)
