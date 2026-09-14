from fastapi.testclient import TestClient

from home_dns.api.app import create_app
from home_dns.config.settings import Environment
from home_dns.core.models import HealthStatus, ProviderHealth
from home_dns.providers.base import DnsProvider, ProviderUnavailableError
from home_dns.providers.mock import MockDnsProvider


class _FailingProvider(MockDnsProvider):
    @property
    def name(self) -> str:
        return "failing"

    def health(self) -> ProviderHealth:
        raise ProviderUnavailableError("unreachable")


def _client(provider: DnsProvider, env: Environment = Environment.DEVELOPMENT) -> TestClient:
    return TestClient(create_app(environment=env, provider=provider))


def test_health_ok() -> None:
    response = _client(MockDnsProvider()).get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"] == "development"
    assert body["provider"] == {"name": "mock", "status": "ok"}


def test_health_degraded_is_still_200() -> None:
    response = _client(MockDnsProvider(health_status=HealthStatus.DEGRADED)).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


def test_health_down_returns_503() -> None:
    response = _client(MockDnsProvider(health_status=HealthStatus.DOWN)).get("/api/v1/health")
    assert response.status_code == 503


def test_provider_error_is_reported_as_down() -> None:
    response = _client(_FailingProvider()).get("/api/v1/health")
    assert response.status_code == 503
    assert response.json()["provider"] == {"name": "failing", "status": "down"}


def test_api_docs_only_outside_production() -> None:
    assert _client(MockDnsProvider()).get("/api/openapi.json").status_code == 200
    prod = _client(MockDnsProvider(), Environment.PRODUCTION)
    assert prod.get("/api/openapi.json").status_code == 404
    assert prod.get("/api/docs").status_code == 404
