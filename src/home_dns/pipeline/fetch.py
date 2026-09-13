"""HTTP fetching for blocklist sources.

The fetcher only transports bytes. Every content decision (status, type, size, format,
freshness) is made by the pipeline, so a successful download is never trusted by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from home_dns import __version__

USER_AGENT = f"home-dns/{__version__} (+blocklist pipeline)"


class FetchError(Exception):
    """Transport-level failure: DNS, connection, timeout, TLS, or body larger than allowed."""


@dataclass(frozen=True)
class FetchResponse:
    url: str
    status: int
    content_type: str | None
    body: bytes


class Fetcher(Protocol):
    def fetch(self, url: str, *, max_bytes: int) -> FetchResponse: ...


class HttpxFetcher:
    """Streams the body and aborts once ``max_bytes`` is exceeded. Redirects are not followed."""

    def __init__(
        self, *, timeout_seconds: float = 30.0, client: httpx.Client | None = None
    ) -> None:
        self._client = client or httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT},
        )

    def fetch(self, url: str, *, max_bytes: int) -> FetchResponse:
        try:
            with self._client.stream("GET", url) as response:
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise FetchError(f"{url}: body exceeds {max_bytes} bytes")
                    chunks.append(chunk)
                return FetchResponse(
                    url=url,
                    status=response.status_code,
                    content_type=response.headers.get("content-type"),
                    body=b"".join(chunks),
                )
        except httpx.HTTPError as exc:
            raise FetchError(f"{url}: {type(exc).__name__}: {exc}") from exc
