"""Builders for synthetic blocklists and a scripted fetcher (no network)."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from home_dns.pipeline.fetch import FetchError, FetchResponse


def adblock_list(
    domains: Iterable[str],
    *,
    last_modified: datetime | None,
    declared: int | None = None,
    version: str = "2026.0913.0800.00",
    extra_lines: Iterable[str] = (),
) -> str:
    rules = [f"||{d}^" for d in domains] + list(extra_lines)
    header = ["[Adblock Plus]", "! Title: Test list", "! Expires: 8 hours"]
    if last_modified is not None:
        header.append(f"! Last modified: {last_modified.strftime('%d %b %Y %H:%M')} UTC")
    header.append(f"! Version: {version}")
    header.append(f"! Number of entries: {len(rules) if declared is None else declared}")
    header.append("!")
    # pad so fixtures clear the pipeline's minimum-size guard
    padding = [f"! padding {i:04d} " + "x" * 40 for i in range(30)]
    return "\n".join(header + padding + rules) + "\n"


def domains(count: int, prefix: str = "ads") -> list[str]:
    return [f"{prefix}{i}.blocked.example" for i in range(count)]


class ScriptedFetcher:
    """Returns a scripted response or raises a scripted error per URL, and records calls."""

    def __init__(self, script: dict[str, FetchResponse | Exception]) -> None:
        self.script = script
        self.calls: list[str] = []

    def fetch(self, url: str, *, max_bytes: int) -> FetchResponse:
        self.calls.append(url)
        outcome = self.script.get(url, FetchError(f"{url}: not scripted"))
        if isinstance(outcome, Exception):
            raise outcome
        if len(outcome.body) > max_bytes:
            raise FetchError(f"{url}: body exceeds {max_bytes} bytes")
        return outcome


def ok(url: str, text: str, content_type: str = "text/plain; charset=utf-8") -> FetchResponse:
    return FetchResponse(url=url, status=200, content_type=content_type, body=text.encode("utf-8"))
