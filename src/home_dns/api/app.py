"""FastAPI application factory."""

from __future__ import annotations

import threading
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from pydantic import BaseModel

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


def create_app(
    *,
    environment: Environment,
    provider: DnsProvider,
    dashboard: DashboardContext | None = None,
) -> FastAPI:
    """Without ``dashboard`` only the public health endpoint exists."""
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

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers.update(_SECURITY_HEADERS)
        if request.url.path.startswith("/api/v1"):
            response.headers["Content-Security-Policy"] = _API_CSP
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

    return app
