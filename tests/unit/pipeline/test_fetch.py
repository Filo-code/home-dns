import httpx
import pytest

from home_dns.pipeline.fetch import USER_AGENT, FetchError, HttpxFetcher


def _fetcher(handler) -> HttpxFetcher:  # type: ignore[no-untyped-def]
    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT},
    )
    return HttpxFetcher(client=client)


def test_successful_fetch_returns_status_type_and_body() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, headers={"content-type": "text/plain"}, content=b"hello")

    response = _fetcher(handler).fetch("https://cdn.example/list.txt", max_bytes=100)
    assert (response.status, response.content_type, response.body) == (200, "text/plain", b"hello")
    assert seen[0].headers["user-agent"].startswith("home-dns/")


def test_non_200_is_returned_for_the_pipeline_to_judge() -> None:
    response = _fetcher(lambda r: httpx.Response(503, content=b"down")).fetch(
        "https://cdn.example/x", max_bytes=100
    )
    assert response.status == 503


def test_redirects_are_not_followed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://evil.example/list.txt"})

    assert _fetcher(handler).fetch("https://cdn.example/x", max_bytes=100).status == 302


def test_body_larger_than_limit_is_aborted() -> None:
    handler = lambda r: httpx.Response(200, content=b"x" * 1000)  # noqa: E731
    with pytest.raises(FetchError, match="exceeds 100 bytes"):
        _fetcher(handler).fetch("https://cdn.example/x", max_bytes=100)


def test_transport_errors_become_fetch_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    with pytest.raises(FetchError, match="ConnectTimeout"):
        _fetcher(handler).fetch("https://cdn.example/x", max_bytes=100)


def test_default_client_construction() -> None:
    assert HttpxFetcher(timeout_seconds=1.0) is not None
