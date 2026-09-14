"""A8: FastAPI serving the built frontend (docs/adr/0010-frontend-hosting.md).

`create_app(..., static_dir=...)` must serve the SPA at `/`, fall back to `index.html` for
client-side routes, serve real assets with real 404s for missing ones, never shadow `/api/v1/*`,
and apply the frontend CSP only to non-API responses. All against a small fake `dist/`, not a
real `vite build` (that is exercised separately by `npm run build` + `make serve-static`).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from home_dns.api.app import create_app
from home_dns.config.settings import Environment
from home_dns.providers.mock import MockDnsProvider

INDEX_HTML = "<!doctype html><html><body>home-dns dashboard</body></html>"


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (root / "assets" / "app.js").write_text("console.log('ok');" * 100, encoding="utf-8")
    (root / "favicon.ico").write_bytes(b"\x00" * 16)
    return root


def _client(static_dir: Path | None) -> TestClient:
    return TestClient(
        create_app(
            environment=Environment.DEVELOPMENT, provider=MockDnsProvider(), static_dir=static_dir
        )
    )


def test_without_static_dir_root_is_a_plain_404(dist: Path) -> None:
    response = _client(None).get("/")
    assert response.status_code == 404
    assert response.json()["detail"] != INDEX_HTML


def test_root_serves_the_spa(dist: Path) -> None:
    response = _client(dist).get("/")
    assert response.status_code == 200
    assert response.text == INDEX_HTML
    assert response.headers["content-type"].startswith("text/html")


@pytest.mark.parametrize("path", ["/login", "/devices", "/devices/42", "/security/", "/unknown"])
def test_client_side_routes_fall_back_to_the_spa(dist: Path, path: str) -> None:
    response = _client(dist).get(path)
    assert response.status_code == 200
    assert response.text == INDEX_HTML


def test_a_real_root_level_file_is_served_directly(dist: Path) -> None:
    response = _client(dist).get("/favicon.ico")
    assert response.status_code == 200
    assert response.content == b"\x00" * 16


def test_real_assets_are_served_with_caching_headers(dist: Path) -> None:
    response = _client(dist).get("/assets/app.js")
    assert response.status_code == 200
    assert "console.log" in response.text
    assert response.headers.get("etag") or response.headers.get("last-modified")


def test_missing_asset_is_a_real_404_not_the_spa(dist: Path) -> None:
    response = _client(dist).get("/assets/does-not-exist.js")
    assert response.status_code == 404
    assert response.text != INDEX_HTML


def test_api_routes_are_never_shadowed_by_the_spa(dist: Path) -> None:
    client = _client(dist)
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"


def test_unknown_api_path_is_a_real_404_not_the_spa(dist: Path) -> None:
    response = _client(dist).get("/api/v1/this-route-does-not-exist")
    assert response.status_code == 404
    assert response.text != INDEX_HTML


def test_missing_dist_directory_serves_a_clear_404(tmp_path: Path) -> None:
    response = _client(tmp_path / "never-built").get("/")
    assert response.status_code == 404


def test_path_traversal_outside_static_dir_is_refused(tmp_path: Path, dist: Path) -> None:
    secret = tmp_path / "outside-static-dir.txt"
    secret.write_text("must never be served", encoding="utf-8")
    # httpx normalises literal ".." before sending; percent-encoding survives client-side
    # normalisation so the server is the one that decodes and must reject it.
    response = _client(dist).get("/assets/%2e%2e/%2e%2e/outside-static-dir.txt")
    assert "must never be served" not in response.text


def test_frontend_csp_applies_to_html_not_to_the_api(dist: Path) -> None:
    client = _client(dist)
    page = client.get("/")
    api = client.get("/api/v1/health")
    assert page.headers["content-security-policy"].startswith("default-src 'self'")
    assert "script-src 'self'" in page.headers["content-security-policy"]
    assert api.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"


def test_no_csp_without_static_dir_on_non_api_paths() -> None:
    response = _client(None).get("/")
    assert "content-security-policy" not in response.headers


def test_gzip_compresses_large_responses(dist: Path) -> None:
    response = _client(dist).get("/assets/app.js")
    assert response.headers.get("content-encoding") == "gzip"


def test_security_headers_still_present_on_static_responses(dist: Path) -> None:
    response = _client(dist).get("/")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
