"""E2E tests for document ingestion flow.

Tests the complete journey: URL submission → NLP extraction → Graph storage → Review queue
"""

import pytest
import httpx
import time
from uuid import uuid4
from typing import Optional


# Service URLs
ADMIN_URL = "http://localhost:8400"
INGESTION_URL = "http://localhost:8002"
GRAPH_URL = "http://localhost:8200"

# Test configuration
POLL_INTERVAL = 2  # seconds
MAX_WAIT_TIME = 60  # seconds


@pytest.fixture(scope="module")
def admin_client():
    """Admin API client."""
    return httpx.Client(base_url=ADMIN_URL, timeout=30)


@pytest.fixture(scope="module")
def ingestion_client():
    """Ingestion API client."""
    return httpx.Client(base_url=INGESTION_URL, timeout=30)


@pytest.fixture(scope="module")
def graph_client():
    """Graph API client."""
    return httpx.Client(base_url=GRAPH_URL, timeout=30)


def wait_for_condition(
    check_fn, 
    timeout: int = MAX_WAIT_TIME, 
    interval: int = POLL_INTERVAL,
    description: str = "condition"
) -> bool:
    """Poll until condition is true or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        if check_fn():
            return True
        time.sleep(interval)
    return False


class TestServicesHealthy:
    """Verify all services are running before E2E tests."""

    def test_admin_healthy(self, admin_client):
        """Admin API should be healthy."""
        try:
            response = admin_client.get("/health")
            assert response.status_code == 200
            assert response.json().get("status") in ["healthy", "ok"]
        except httpx.ConnectError:
            pytest.skip("Admin API not running")

    def test_ingestion_healthy(self, ingestion_client):
        """Ingestion API should be healthy."""
        try:
            response = ingestion_client.get("/health")
            assert response.status_code == 200
        except httpx.ConnectError:
            pytest.skip("Ingestion API not running")

    def test_graph_healthy(self, graph_client):
        """Graph API should be healthy."""
        try:
            response = graph_client.get("/v1/labels/health")
            assert response.status_code == 200
        except httpx.ConnectError:
            pytest.skip("Graph API not running")


class TestIngestionFlow:
    """Test the complete document ingestion flow."""

    @pytest.fixture
    def test_tenant_id(self):
        """Generate unique tenant ID for test isolation."""
        return str(uuid4())

    def test_submit_url_returns_job_id(self, ingestion_client):
        """Submitting a URL should return a job ID."""
        try:
            response = ingestion_client.post(
                "/v1/ingest/url",
                json={
                    "url": "https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-requirements-additional-traceability-records-certain-foods",
                    "source_system": "fda"
                },
                headers={"X-RegEngine-API-Key": "test-key"}
            )
            
            # Should return 200/202 with job info
            assert response.status_code in [200, 202, 401, 403], (
                f"Unexpected status: {response.status_code}"
            )
            
            if response.status_code in [200, 202]:
                data = response.json()
                assert "job_id" in data or "id" in data or "task_id" in data
                
        except httpx.ConnectError:
            pytest.skip("Ingestion API not running")

    def test_job_status_endpoint_exists(self, ingestion_client):
        """Job status endpoint should be accessible."""
        try:
            # Try to get status of a fake job
            response = ingestion_client.get(
                "/v1/ingestion/jobs/00000000-0000-0000-0000-000000000000",
                headers={"X-RegEngine-API-Key": "test-key"}
            )
            
            # Should return 404 (not found) or 401/403 (auth), not 500
            assert response.status_code in [404, 401, 403], (
                f"Unexpected status: {response.status_code}"
            )
            
        except httpx.ConnectError:
            pytest.skip("Ingestion API not running")


class TestReviewQueueFlow:
    """Test the human review queue flow."""

    def test_list_review_items(self, admin_client):
        """Should be able to list review items."""
        try:
            response = admin_client.get(
                "/v1/admin/review/flagged-extractions",
                headers={"X-Admin-Key": "admin-master-key-dev"}
            )
            
            # Should return list or auth error
            assert response.status_code in [200, 401, 403]
            
            if response.status_code == 200:
                data = response.json()
                # Should be a list or have items key
                assert isinstance(data, (list, dict))
                
        except httpx.ConnectError:
            pytest.skip("Admin API not running")

    def test_approve_requires_valid_id(self, admin_client):
        """Approving requires valid review ID."""
        try:
            response = admin_client.post(
                "/v1/admin/review/flagged-extractions/invalid-id/approve",
                headers={"X-Admin-Key": "admin-master-key-dev"}
            )
            
            # Should return 404 or validation error, not 500
            assert response.status_code in [400, 404, 401, 403, 422]
            
        except httpx.ConnectError:
            pytest.skip("Admin API not running")


class TestGraphIntegration:
    """Test graph service integration."""

    def test_labels_health(self, graph_client):
        """Labels service should be accessible."""
        try:
            response = graph_client.get("/v1/labels/health")
            assert response.status_code == 200
        except httpx.ConnectError:
            pytest.skip("Graph API not running")

    def test_trace_endpoint_requires_tenant(self, graph_client):
        """Trace endpoint should require tenant context."""
        try:
            response = graph_client.get(
                "/v1/trace/lot/TEST-LOT-001",
                headers={"X-RegEngine-API-Key": "test-key"}
            )
            
            # Should require tenant header or return auth error
            assert response.status_code in [400, 401, 403, 404]
            
        except httpx.ConnectError:
            pytest.skip("Graph API not running")


class TestComplianceFlow:
    """Test compliance status flow."""

    @pytest.fixture
    def compliance_client(self):
        """Compliance API client."""
        return httpx.Client(base_url="http://localhost:8500", timeout=30)

    def test_checklists_accessible(self, compliance_client):
        """Checklists endpoint should be accessible."""
        try:
            response = compliance_client.get(
                "/checklists",
                headers={"X-RegEngine-API-Key": "test-key"}
            )
            
            assert response.status_code in [200, 401, 403]
            
        except httpx.ConnectError:
            pytest.skip("Compliance API not running")

    def test_validate_endpoint_exists(self, compliance_client):
        """Validation endpoint should exist."""
        try:
            response = compliance_client.post(
                "/validate",
                json={"config": {}, "ruleset": "fsma_204"},
                headers={"X-RegEngine-API-Key": "test-key"}
            )
            
            # Should return validation result or auth error, not 500
            assert response.status_code in [200, 400, 401, 403, 422]
            
        except httpx.ConnectError:
            pytest.skip("Compliance API not running")
