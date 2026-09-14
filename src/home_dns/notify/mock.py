"""In-memory Notifier for development and tests."""

from __future__ import annotations

from home_dns.notify.base import Notifier, OutgoingMessage, SendResult


class MockNotifier(Notifier):
    def __init__(self) -> None:
        self.sent: list[OutgoingMessage] = []

    @property
    def name(self) -> str:
        return "mock"

    def send(self, message: OutgoingMessage, *, dry_run: bool = True) -> SendResult:
        if dry_run:
            return SendResult(sent=False, detail="dry-run: not sent")
        self.sent.append(message)
        return SendResult(sent=True, detail="recorded in memory")
