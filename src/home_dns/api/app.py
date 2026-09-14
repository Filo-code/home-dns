"""FastAPI application factory."""

from __future__ import annotations

import threading
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.middleware.gzip import GZipMiddleware
from starlette.staticfiles import StaticFiles

from home_dns import __version__
from home_dns.api import auth, views
from home_dns.api.context import DashboardContext
from home_dns.config.settings import Environment
from home_dns.core.models import HealthStatus
from home_dns.providers.base import DnsProvider, ProviderError


class ProviderHealthView(BaseModel):
    name: str
    status: HealthStatus


class HealthResponse(BaseModel):
    status: HealthStatus
    environment: Environment
    provider: ProviderHealthView
    version: str


_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}
# JSON endpoints only: the development-only /api/docs page loads its own assets.
_API_CSP = "default-src 'none'; frame-ancestors 'none'"
# The static frontend (A8): a same-origin SPA needs to load its own script/style/images and
# call its own API, nothing else. Verified against the real `vite build` output in
# tests/api/test_static_hosting.py rather than assumed.
_FRONTEND_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


def create_app(
    *,
    environment: Environment,
    provider: DnsProvider,
    dashboard: DashboardContext | None = None,
    static_dir: Path | None = None,
) -> FastAPI:
    """Without ``dashboard`` only the public health endpoint exists.

    ``static_dir``, when given, serves the built frontend (``vite build``'s ``dist/``) from the
    same process and origin as the API (docs/adr/0010-frontend-hosting.md) — no nginx, no
    Node.js at runtime. The API routers are always registered first, and the SPA catch-all route
    added last, so ``/api/v1/*`` can never be shadowed by the frontend.
    """
    production = environment is Environment.PRODUCTION

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        runner = dashboard.collector if dashboard else None
        stop = threading.Event()
        thread = None
        if runner is not None:
            thread = threading.Thread(
                target=runner.collector.run,
                args=(stop,),
                kwargs={
                    "poll_interval": runner.poll_interval_seconds,
                    "flush_interval": runner.flush_interval_seconds,
                },
                name="metrics-collector",
                daemon=True,
            )
            thread.start()
        try:
            yield
        finally:
            stop.set()
            if thread is not None:
                thread.join(timeout=30)

    app = FastAPI(
        title="home-dns",
        version=__version__,
        docs_url=None if production else "/api/docs",
        redoc_url=None,
        openapi_url=None if production else "/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.provider = provider
    # Outermost among user middleware (added last -> wraps closest to the client); compresses
    # whatever body the router/StaticFiles below eventually produce, API or static alike.
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers.update(_SECURITY_HEADERS)
        if request.url.path.startswith("/api/v1"):
            response.headers["Content-Security-Policy"] = _API_CSP
        elif static_dir is not None:
            response.headers["Content-Security-Policy"] = _FRONTEND_CSP
        return response

    if dashboard is not None:
        app.state.dashboard = dashboard
        app.include_router(auth.router)
        app.include_router(views.router)

    @app.get("/api/v1/health", response_model=HealthResponse)
    def health(response: Response) -> HealthResponse:
        try:
            provider_status = provider.health().status
        except ProviderError:
            provider_status = HealthStatus.DOWN
        if provider_status is HealthStatus.DOWN:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(
            status=provider_status,
            environment=environment,
            provider=ProviderHealthView(name=provider.name, status=provider_status),
            version=__version__,
        )

    if static_dir is not None:
        _mount_static_frontend(app, static_dir)

    return app


def _mount_static_frontend(app: FastAPI, static_dir: Path) -> None:
    """Serve a `vite build` output. Registered after every API route above, so an unmatched
    `/api/*` path 404s instead of falling through to the SPA (checked explicitly below too,
    since route-registration order alone is easy to get wrong on a future refactor)."""
    assets_dir = static_dir / "assets"
    if assets_dir.is_dir():
        # Real files, real 404s for a missing hashed bundle: no HTML fallback here.
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    index_file = static_dir / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        if full_path and ".." not in Path(full_path).parts:
            candidate = static_dir / full_path
            if candidate.is_file():
                return FileResponse(candidate)
        if not index_file.is_file():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "frontend build not found")
        return FileResponse(index_file)
