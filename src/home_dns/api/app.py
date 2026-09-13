"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI, Response, status
from pydantic import BaseModel

from home_dns import __version__
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


def create_app(*, environment: Environment, provider: DnsProvider) -> FastAPI:
    production = environment is Environment.PRODUCTION
    app = FastAPI(
        title="home-dns",
        version=__version__,
        docs_url=None if production else "/api/docs",
        redoc_url=None,
        openapi_url=None if production else "/api/openapi.json",
    )

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
