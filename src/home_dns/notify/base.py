"""The Notifier interface.

Every implementation (MockNotifier, FileNotifier, TelegramNotifier) receives plain values,
never configuration objects — the same rule providers/base.py states for DnsProvider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from home_dns.core.notify import Severity


class NotifierError(Exception):
    """Base class for all notifier failures."""


class NotifierConfigError(NotifierError):
    """The selected notifier cannot be constructed (e.g. missing Telegram secrets)."""


@dataclass(frozen=True)
class OutgoingMessage:
    severity: Severity
    event: str
    text: str


@dataclass(frozen=True)
class SendResult:
    sent: bool
    detail: str


class Notifier(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Stable identifier, e.g. 'mock', 'file' or 'telegram'."""

    @abstractmethod
    def send(self, message: OutgoingMessage, *, dry_run: bool = True) -> SendResult:
        """Never raises for a delivery failure — returns sent=False instead."""
