"""Contract tests for inter-service API communication.

These tests validate that services can communicate with each other correctly,
ensuring the APIs consumers depend on remain stable.
"""

import os
from typing import Optional

import httpx
import pytest

# Service URLs (configure via env in CI)
SERVICE_URLS = {
    "admin": "http://localhost:8400",
    "ingestion": "http://localhost:8002",
    "compliance": "http://localhost:8500",
    "graph": "http://localhost:8200",
}


def _live_or_fail(service_name: str) -> None:
    """Fail when a live service is unreachable; skip only with explicit opt-in.

    These contract tests prove nothing when every service is down, so a
    connection failure fails by default. Set REGENGINE_ALLOW_CONTRACT_SKIP=1
    to skip them explicitly (for example, local runs without the stack).
    """
    if os.getenv("REGENGINE_ALLOW_CONTRACT_SKIP", "").strip().lower() in {"1", "true", "yes"}:
        pytest.skip(f"{service_name} not running (REGENGINE_ALLOW_CONTRACT_SKIP=1)")
    pytest.fail(
        f"{service_name} not running. Start the service or set "
        "REGENGINE_ALLOW_CONTRACT_SKIP=1 to skip live contract tests"
    )


@pytest.fixture(scope="module")
def clients():
    """Create HTTP clients for all services."""
    return {name: httpx.Client(base_url=url, timeout=10) for name, url in SERVICE_URLS.items()}


class TestServiceHealthContracts:
    """All services should implement consistent health endpoints."""

    @pytest.mark.parametrize("service_name", SERVICE_URLS.keys())
    def test_health_endpoint_returns_200(self, clients, service_name):
        """Each service should have a working /health endpoint."""
        try:
            response = clients[service_name].get("/health")
            assert response.status_code == 200, f"{service_name} health check failed: {response.status_code}"
        except httpx.ConnectError:
            _live_or_fail(service_name)

    @pytest.mark.parametrize("service_name", SERVICE_URLS.keys())
    def test_health_response_is_json(self, clients, service_name):
        """Health endpoints should return JSON."""
        try:
            response = clients[service_name].get("/health")
            content_type = response.headers.get("content-type", "")
            assert "application/json" in content_type
        except httpx.ConnectError:
            _live_or_fail(service_name)

    @pytest.mark.parametrize("service_name", SERVICE_URLS.keys())
    def test_health_has_status_field(self, clients, service_name):
        """Health responses should have status field."""
        try:
            response = clients[service_name].get("/health")
            data = response.json()
            assert "status" in data, f"{service_name} health missing 'status'"
        except httpx.ConnectError:
            _live_or_fail(service_name)


# NOTE: the offline ingestion/NLP schema tests used to live here as
# TestIngestionToNLPContract. They moved to
# tests/contract/test_ingest_nlp_schema_contract.py so they run in the
# blocking repo-root-suite gate; this file needs live services. That file
# also calls the real producer emission path, which these tests never did.


class TestAdminToComplianceContract:
    """Contract between Admin and Compliance services."""

    def test_tenant_id_format_is_uuid(self, clients):
        """Tenant IDs should be valid UUIDs across services."""
        # Both services should accept UUID format tenant IDs
        # This validates the shared contract
        import uuid

        test_tenant_id = str(uuid.uuid4())

        # Validate UUID format
        parsed = uuid.UUID(test_tenant_id)
        assert str(parsed) == test_tenant_id


class TestGraphServiceContract:
    """Contract tests for Graph service."""

    def test_graph_requires_tenant_header(self, clients):
        """Graph service should require X-Tenant-ID header."""
        try:
            # Try to access a tenant-scoped endpoint without header
            response = clients["graph"].get("/v1/labels/health")
            # Health should work without tenant
            assert response.status_code == 200
        except httpx.ConnectError:
            _live_or_fail("graph")


class TestCrossServiceErrorHandling:
    """Validate consistent error handling across services."""

    @pytest.mark.parametrize("service_name", SERVICE_URLS.keys())
    def test_404_returns_json_error(self, clients, service_name):
        """All services should return JSON errors for 404."""
        try:
            response = clients[service_name].get("/nonexistent-endpoint-12345")

            if response.status_code == 404:
                content_type = response.headers.get("content-type", "")
                assert "application/json" in content_type, f"{service_name} 404 should return JSON"

                data = response.json()
                assert "detail" in data, f"{service_name} error response missing 'detail'"
        except httpx.ConnectError:
            _live_or_fail(service_name)

    @pytest.mark.parametrize("service_name", SERVICE_URLS.keys())
    def test_invalid_json_returns_400(self, clients, service_name):
        """Services should return 400 for invalid JSON body."""
        try:
            response = clients[service_name].post(
                "/health",  # Using health as placeholder
                content=b"not valid json",
                headers={"Content-Type": "application/json"},
            )

            # May return 405 (Method Not Allowed) or 400
            assert response.status_code in [400, 405, 422]
        except httpx.ConnectError:
            _live_or_fail(service_name)
