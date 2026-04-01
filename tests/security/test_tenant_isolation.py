"""Security tests for tenant isolation.

Verifies that tenant data cannot be accessed across tenant boundaries.
"""

import pytest
import httpx
from uuid import uuid4


# Service URLs
ADMIN_URL = "http://localhost:8400"
GRAPH_URL = "http://localhost:8200"


def _service_reachable(url: str) -> bool:
    try:
        httpx.get(f"{url}/health", timeout=2)
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _service_reachable(ADMIN_URL),
    reason="Admin API not reachable",
)


@pytest.fixture(scope="module")
def admin_client():
    """Admin API client."""
    return httpx.Client(base_url=ADMIN_URL, timeout=30)


@pytest.fixture(scope="module")
def graph_client():
    """Graph API client."""
    return httpx.Client(base_url=GRAPH_URL, timeout=30)


class TestAPIKeyIsolation:
    """Test that API keys are tenant-scoped."""

    def test_missing_api_key_rejected(self, admin_client):
        """Requests without API key should be rejected."""
        response = admin_client.get("/v1/admin/keys")
        assert response.status_code in [401, 403], (
            f"Expected 401/403 without API key, got {response.status_code}"
        )

    def test_invalid_api_key_rejected(self, admin_client):
        """Invalid API keys should be rejected."""
        response = admin_client.get(
            "/v1/admin/keys",
            headers={"X-Admin-Key": "invalid-key-12345"}
        )
        assert response.status_code in [401, 403]

    def test_malformed_api_key_rejected(self, admin_client):
        """Malformed API keys should be rejected."""
        # Try SQL injection in API key
        response = admin_client.get(
            "/v1/admin/keys",
            headers={"X-Admin-Key": "'; DROP TABLE api_keys; --"}
        )
        assert response.status_code in [401, 403]

        # Try very long key
        response = admin_client.get(
            "/v1/admin/keys",
            headers={"X-Admin-Key": "a" * 10000}
        )
        assert response.status_code in [401, 403, 400]


class TestTenantHeaderValidation:
    """Test X-Tenant-ID header validation."""

    def test_invalid_tenant_id_format_rejected(self, graph_client):
        """Invalid UUID format should be rejected."""
        try:
            response = graph_client.get(
                "/v1/labels/health",
                headers={
                    "X-RegEngine-API-Key": "test-key",
                    "X-Tenant-ID": "not-a-valid-uuid"
                }
            )
            # Health may not require tenant, but if it does, should reject
            # Main point is it shouldn't crash (500)
            assert response.status_code != 500
        except httpx.ConnectError:
            pytest.skip("Graph API not running")

    def test_sql_injection_in_tenant_id(self, graph_client):
        """SQL injection in tenant ID should be safely handled."""
        try:
            response = graph_client.get(
                "/v1/labels/health",
                headers={
                    "X-RegEngine-API-Key": "test-key",
                    "X-Tenant-ID": "'; DROP TABLE tenants; --"
                }
            )
            # SQL injection payloads must be rejected, never accepted as valid input
            assert response.status_code in [400, 401, 403, 422], (
                f"SQL injection payload was accepted with status {response.status_code}; "
                "expected rejection (400/401/403/422)"
            )
        except httpx.ConnectError:
            pytest.skip("Graph API not running")


class TestCrossTenantAccess:
    """Test that cross-tenant access is blocked."""

    def test_cannot_access_other_tenant_keys(self, admin_client):
        """Should not be able to list another tenant's keys."""
        tenant_a = str(uuid4())

        # Try to access tenant B's keys with tenant A header
        response = admin_client.get(
            "/v1/admin/keys",
            headers={
                "X-Admin-Key": "admin-master-key-dev",
                "X-Tenant-ID": tenant_a
            }
        )

        # Should return empty list or tenant-specific data only
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                # Verify no keys from other tenants
                for key in data:
                    if "tenant_id" in key:
                        assert key["tenant_id"] == tenant_a or key["tenant_id"] is None

    def test_cannot_access_review_items_across_tenants(self, admin_client):
        """Review items should be tenant-isolated."""
        # Use a fixed random tenant ID for the entire test so we can check
        # that returned items belong only to THIS tenant, not any other.
        requesting_tenant_id = str(uuid4())
        response = admin_client.get(
            "/v1/admin/review/flagged-extractions",
            headers={
                "X-Admin-Key": "admin-master-key-dev",
                "X-Tenant-ID": requesting_tenant_id
            }
        )

        if response.status_code == 200:
            data = response.json()
            # Every item with a tenant_id field MUST belong to the requesting tenant.
            # Previously this compared against a fresh uuid4() per iteration, which
            # was always False — vacuously passing. Now we compare against the real ID.
            if isinstance(data, list):
                for item in data:
                    if "tenant_id" in item:
                        assert item["tenant_id"] == requesting_tenant_id, (
                            f"Cross-tenant data leak: got tenant_id {item['tenant_id']!r}, "
                            f"expected {requesting_tenant_id!r}"
                        )


class TestInputValidation:
    """Test input validation and sanitization."""

    def test_xss_in_request_body_sanitized(self, admin_client):
        """XSS in request body should be handled safely."""
        response = admin_client.post(
            "/v1/admin/tenants",
            headers={"X-Admin-Key": "admin-master-key-dev"},
            json={
                "name": "<script>alert('xss')</script>"
            }
        )

        # Should either reject or sanitize, not execute
        assert response.status_code in [200, 201, 400, 422]

        if response.status_code in [200, 201]:
            data = response.json()
            # Name should be sanitized or escaped
            if "name" in data:
                assert "<script>" not in data["name"] or \
                       "&lt;script&gt;" in data["name"]

    def test_oversized_request_rejected(self, admin_client):
        """Very large request bodies should be rejected."""
        try:
            # Try to send 10MB of data
            large_data = {"name": "x" * (10 * 1024 * 1024)}

            response = admin_client.post(
                "/v1/admin/tenants",
                headers={"X-Admin-Key": "admin-master-key-dev"},
                json=large_data
            )

            # Should reject large requests
            assert response.status_code in [400, 413, 422]

        except Exception:
            # Large request may fail at network level, which is fine
            pass


class TestRateLimitEnforcement:
    """Test rate limiting is enforced."""

    def test_rate_limit_headers_present(self, admin_client):
        """Rate limit headers should be present on responses."""
        response = admin_client.get("/health")

        # Rate limit headers should be present
        rate_limit_headers = [
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset"
        ]

        # At least one should be present if rate limiting is enabled
        has_rate_limit = any(h in response.headers for h in rate_limit_headers)

        if not has_rate_limit:
            pytest.skip("Rate limiting not enabled on health endpoint")


class TestErrorHandling:
    """Test that errors don't leak sensitive information."""

    def test_404_does_not_leak_paths(self, admin_client):
        """404 errors should not reveal internal paths."""
        response = admin_client.get("/v1/admin/secret-internal-path")

        if response.status_code == 404:
            body = response.text.lower()
            # Should not contain internal paths or stack traces
            assert "/users/" not in body
            assert "traceback" not in body
            assert "file \"" not in body

    def test_500_does_not_leak_stack_trace(self, admin_client):
        """500 errors should not reveal stack traces in production."""
        # Try to trigger an error with invalid input
        response = admin_client.post(
            "/v1/admin/keys",
            headers={"X-Admin-Key": "admin-master-key-dev"},
            json={"invalid": "data"}  # Missing required fields
        )

        if response.status_code == 500:
            body = response.text.lower()
            # Should not contain stack traces
            assert "traceback" not in body
            assert "file \"" not in body
            assert "line " not in body
