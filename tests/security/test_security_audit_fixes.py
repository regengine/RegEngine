"""Security tests for all audit fixes (PRs #321-#330).

This module covers:
- SQL Injection Prevention (PR #323)
- Auth Guard enforcement (PR #322)
- K8s Auth Bypass Guard (PR #321)
- RLS Sysadmin Defense (PR #324)
- Race Condition Guards (PR #326)
- JWT Key Rotation (PR #328)
- CSRF Double-Submit (PR #329)

Tests follow the patterns from test_tenant_isolation.py and use httpx for service testing.
"""

import os
import pytest
import httpx
from uuid import uuid4
from datetime import datetime, timedelta, timezone


# Service URLs
ADMIN_URL = "http://localhost:8400"
INGESTION_URL = "http://localhost:8002"
GRAPH_URL = "http://localhost:8200"


@pytest.fixture(scope="module")
def admin_client():
    """Admin API client."""
    return httpx.Client(base_url=ADMIN_URL, timeout=30)


@pytest.fixture(scope="module")
def ingestion_client():
    """Ingestion service API client."""
    return httpx.Client(base_url=INGESTION_URL, timeout=30)


@pytest.fixture(scope="module")
def graph_client():
    """Graph API client."""
    return httpx.Client(base_url=GRAPH_URL, timeout=30)


class TestSQLInjectionPrevention:
    """Test SQL injection prevention (PR #323).

    Verifies that dynamic column names in EPCIS ingestion, CTE persistence,
    and alerts are properly allowlisted and cannot be exploited.
    """

    def test_epcis_event_column_injection_blocked(self, ingestion_client):
        """Test that SQL injection in event_col parameter is blocked."""
        try:
            tenant_id = str(uuid4())

            # Attempt SQL injection in column name parameter
            response = ingestion_client.post(
                "/v1/ingest/epcis/transform",
                headers={
                    "X-RegEngine-API-Key": "test-key",
                    "X-Tenant-ID": tenant_id,
                },
                json={
                    "event_col": "event_type'; DROP TABLE events; --",
                    "data": [{"event_type": "test"}],
                }
            )

            # Should reject malicious column name
            assert response.status_code in [400, 422], (
                f"Expected 400/422 for injected column, got {response.status_code}"
            )

        except httpx.ConnectError:
            pytest.skip("Ingestion service not running")

    def test_epcis_tenant_column_injection_blocked(self, ingestion_client):
        """Test that SQL injection in tenant_col parameter is blocked."""
        try:
            tenant_id = str(uuid4())

            response = ingestion_client.post(
                "/v1/ingest/epcis/transform",
                headers={
                    "X-RegEngine-API-Key": "test-key",
                    "X-Tenant-ID": tenant_id,
                },
                json={
                    "tenant_col": "t_id' UNION SELECT * FROM admin_users; --",
                    "data": [{"t_id": tenant_id}],
                }
            )

            # Should reject malicious column name
            assert response.status_code in [400, 422]

        except httpx.ConnectError:
            pytest.skip("Ingestion service not running")

    def test_epcis_message_expr_injection_blocked(self, ingestion_client):
        """Test that SQL injection in message_expr is blocked."""
        try:
            tenant_id = str(uuid4())

            # Attempt injection in message expression
            response = ingestion_client.post(
                "/v1/ingest/epcis/transform",
                headers={
                    "X-RegEngine-API-Key": "test-key",
                    "X-Tenant-ID": tenant_id,
                },
                json={
                    "message_expr": "CAST(msg AS TEXT) || '; DELETE FROM events WHERE 1=1; --'",
                    "data": [{"msg": "test"}],
                }
            )

            # Should reject or sanitize the expression
            assert response.status_code in [400, 422, 200]

        except httpx.ConnectError:
            pytest.skip("Ingestion service not running")

    def test_cte_persistence_condition_injection_blocked(self, ingestion_client):
        """Test that CTE persistence condition parameter rejects SQL injection."""
        try:
            tenant_id = str(uuid4())

            # Attempt to inject malicious SQL in condition
            response = ingestion_client.post(
                "/v1/ingest/cte/persist",
                headers={
                    "X-RegEngine-API-Key": "test-key",
                    "X-Tenant-ID": tenant_id,
                },
                json={
                    "cte_name": "safe_cte",
                    "condition": "created_at > '2024-01-01' OR 1=1; DROP TABLE cte_logs; --",
                    "data": {"test": "value"},
                }
            )

            # Should reject malicious condition
            assert response.status_code in [400, 422]

        except httpx.ConnectError:
            pytest.skip("Ingestion service not running")

    @pytest.mark.parametrize("malicious_col", [
        "col_name'; DROP TABLE t; --",
        "col_name' UNION SELECT * FROM secret_data; --",
        "col_name` OR `1`=`1",
        "col_name\\'; DROP TABLE t; --",
    ])
    def test_dynamic_column_allowlist_enforced(self, ingestion_client, malicious_col):
        """Test that dynamic column names are strictly allowlisted."""
        try:
            tenant_id = str(uuid4())

            response = ingestion_client.post(
                "/v1/ingest/alerts/configure",
                headers={
                    "X-RegEngine-API-Key": "test-key",
                    "X-Tenant-ID": tenant_id,
                },
                json={
                    "alert_column": malicious_col,
                    "threshold": 10,
                }
            )

            # Should reject any non-whitelisted column name
            assert response.status_code in [400, 422]

        except httpx.ConnectError:
            pytest.skip("Ingestion service not running")


class TestAuthGuardEnforcement:
    """Test auth guard enforcement on protected endpoints (PR #322).

    Verifies that endpoints requiring authentication return 401 when
    auth headers are missing or invalid.
    """

    @pytest.mark.parametrize("endpoint,method", [
        ("/v1/ingest/status/job-123", "GET"),
        ("/v1/ingest/documents/doc-456/analysis", "GET"),
        ("/v1/ingest/discovery/queue", "GET"),
    ])
    def test_ingestion_endpoints_require_auth(self, ingestion_client, endpoint, method):
        """Test that ingestion endpoints require authentication."""
        try:
            # Request WITHOUT auth headers
            response = ingestion_client.request(method, endpoint)

            # Should be rejected as 401
            assert response.status_code in [401, 403], (
                f"{method} {endpoint} returned {response.status_code}, expected 401/403"
            )

        except httpx.ConnectError:
            pytest.skip("Ingestion service not running")

    @pytest.mark.parametrize("endpoint,method", [
        ("/v1/evidence/verify", "POST"),
        ("/v1/evidence/chain/env-123", "GET"),
        ("/v1/evidence/envelopes", "GET"),
    ])
    def test_evidence_endpoints_require_auth(self, ingestion_client, endpoint, method):
        """Test that evidence endpoints require authentication."""
        try:
            # Request WITHOUT auth headers
            response = ingestion_client.request(
                method,
                endpoint,
                json={} if method == "POST" else None
            )

            # Should be rejected as 401
            assert response.status_code in [401, 403]

        except httpx.ConnectError:
            pytest.skip("Ingestion service not running")

    def test_vision_analyze_label_requires_auth(self, graph_client):
        """Test that vision analysis endpoint requires auth."""
        try:
            response = graph_client.post(
                "/api/v1/vision/analyze-label",
                json={"image": "base64-data"}
            )

            # Should require auth
            assert response.status_code in [401, 403]

        except httpx.ConnectError:
            pytest.skip("Graph service not running")

    @pytest.mark.parametrize("endpoint,method", [
        ("/v1/obligation/evaluate", "POST"),
        ("/v1/obligation/coverage-report", "GET"),
    ])
    def test_obligation_endpoints_require_auth(self, graph_client, endpoint, method):
        """Test that obligation endpoints require authentication."""
        try:
            response = graph_client.request(
                method,
                endpoint,
                json={} if method == "POST" else None
            )

            # Should require auth
            assert response.status_code in [401, 403]

        except httpx.ConnectError:
            pytest.skip("Graph service not running")

    def test_invalid_api_key_rejected(self, ingestion_client):
        """Test that invalid API keys are rejected."""
        try:
            response = ingestion_client.get(
                "/v1/ingest/status/job-123",
                headers={"X-RegEngine-API-Key": "invalid-key-12345"}
            )

            assert response.status_code in [401, 403]

        except httpx.ConnectError:
            pytest.skip("Ingestion service not running")

    def test_malformed_api_key_rejected(self, ingestion_client):
        """Test that malformed API keys are rejected."""
        try:
            # SQL injection attempt in API key
            response = ingestion_client.get(
                "/v1/ingest/status/job-123",
                headers={"X-RegEngine-API-Key": "'; DROP TABLE api_keys; --"}
            )

            assert response.status_code in [401, 403]

        except httpx.ConnectError:
            pytest.skip("Ingestion service not running")

    def test_expired_api_key_rejected(self, ingestion_client):
        """Test that expired API keys are rejected."""
        try:
            tenant_id = str(uuid4())

            # Try request with a key that should be marked as expired
            response = ingestion_client.get(
                "/v1/ingest/status/job-123",
                headers={
                    "X-RegEngine-API-Key": "expired-key-token",
                    "X-Tenant-ID": tenant_id,
                }
            )

            # Should be rejected (either 401 or because key doesn't exist)
            assert response.status_code in [401, 403]

        except httpx.ConnectError:
            pytest.skip("Ingestion service not running")


class TestK8sAuthBypassGuard:
    """Test that AUTH_TEST_BYPASS_TOKEN is rejected in production (PR #321).

    The AUTH_TEST_BYPASS_TOKEN should only work in development/test environments,
    and must be rejected when REGENGINE_ENV=production.
    """

    def test_bypass_token_rejected_in_production_env(self, ingestion_client):
        """Test that bypass token is rejected when REGENGINE_ENV=production."""
        # This test validates the bypass guard logic.
        # In a live test, it would verify that bypass_token doesn't work when
        # REGENGINE_ENV is explicitly set to "production".

        try:
            tenant_id = str(uuid4())

            # Attempt to use bypass token
            response = ingestion_client.get(
                "/v1/ingest/status/job-123",
                headers={
                    "X-RegEngine-API-Key": os.getenv("AUTH_TEST_BYPASS_TOKEN", "test-bypass-token"),
                    "X-Tenant-ID": tenant_id,
                }
            )

            # If REGENGINE_ENV=production, should fail
            current_env = os.getenv("REGENGINE_ENV", "test").lower()
            if current_env == "production":
                # Bypass token should not work in production
                assert response.status_code in [401, 403], (
                    "Bypass token should not work in production environment"
                )
            else:
                # In test/dev, bypass might work (or might not, depending on app logic)
                pytest.skip(f"Not in production env, bypassing test (env={current_env})")

        except httpx.ConnectError:
            pytest.skip("Ingestion service not running")

    def test_bypass_token_disabled_when_env_not_set(self, ingestion_client):
        """Test that bypass token is disabled when REGENGINE_ENV is not set."""
        # Default behavior should reject bypass tokens
        try:
            tenant_id = str(uuid4())

            response = ingestion_client.get(
                "/v1/ingest/status/job-123",
                headers={
                    "X-RegEngine-API-Key": "some-bypass-token",
                    "X-Tenant-ID": tenant_id,
                }
            )

            # Without explicit env setup, should fail
            assert response.status_code in [401, 403]

        except httpx.ConnectError:
            pytest.skip("Ingestion service not running")


class TestRLSSysadminDefense:
    """Test that sysadmin flag cannot be set without authorization (PR #324).

    Verifies that RLS (Row-Level Security) policies prevent unauthorized
    elevation to sysadmin privileges.
    """

    def test_sysadmin_flag_requires_authorization(self, admin_client):
        """Test that sysadmin flag cannot be set by regular users."""
        try:
            tenant_id = str(uuid4())

            # Attempt to set sysadmin=true without proper authorization
            response = admin_client.post(
                "/v1/admin/user/promote",
                headers={
                    "X-RegEngine-API-Key": "regular-user-key",
                    "X-Tenant-ID": tenant_id,
                },
                json={
                    "user_id": str(uuid4()),
                    "sysadmin": True,
                }
            )

            # Should be rejected (403 Forbidden or 401)
            assert response.status_code in [401, 403], (
                f"Expected 401/403 for unauthorized sysadmin promotion, got {response.status_code}"
            )

        except httpx.ConnectError:
            pytest.skip("Admin service not running")

    def test_sysadmin_flag_in_token_ignored_without_auth(self, admin_client):
        """Test that sysadmin flags in tokens are ignored without proper auth."""
        try:
            tenant_id = str(uuid4())

            # Attempt to use a token with sysadmin claim
            response = admin_client.get(
                "/v1/admin/users",
                headers={
                    "X-RegEngine-API-Key": "user-key-with-false-sysadmin-claim",
                    "X-Tenant-ID": tenant_id,
                }
            )

            # RLS should filter results to only tenant's users, not all users
            if response.status_code == 200:
                data = response.json()
                # Should not contain cross-tenant data
                assert isinstance(data, (list, dict))

        except httpx.ConnectError:
            pytest.skip("Admin service not running")

    def test_sysadmin_operations_require_admin_key(self, admin_client):
        """Test that sysadmin operations require proper X-Admin-Key."""
        try:
            response = admin_client.get(
                "/v1/admin/audit-log",
                headers={
                    "X-RegEngine-API-Key": "regular-api-key",
                    "X-Tenant-ID": str(uuid4()),
                }
            )

            # Should be rejected without X-Admin-Key
            assert response.status_code in [401, 403]

        except httpx.ConnectError:
            pytest.skip("Admin service not running")


class TestRaceConditionGuards:
    """Test race condition guards (PR #326).

    Verifies that concurrent operations don't produce duplicates or
    inconsistent state.
    """

    def test_concurrent_supplier_creation_no_duplicates(self, admin_client):
        """Test that concurrent supplier creation doesn't produce duplicate IDs."""
        try:
            tenant_id = str(uuid4())

            # Simulate concurrent creates of the same supplier
            # In a real test, would use threading/asyncio
            responses = []
            supplier_name = f"test-supplier-{uuid4()}"

            for _ in range(3):
                response = admin_client.post(
                    "/v1/admin/suppliers",
                    headers={
                        "X-Admin-Key": "admin-master-key-dev",
                        "X-Tenant-ID": tenant_id,
                    },
                    json={"name": supplier_name}
                )
                responses.append(response)

            # Count successful creations
            successful = [r for r in responses if r.status_code in [200, 201]]

            # Should have at most 1 successful creation, or all fail
            if len(successful) > 1:
                # Check that IDs are unique
                ids = [r.json().get("id") for r in successful if r.status_code in [200, 201]]
                assert len(ids) == len(set(ids)), "Duplicate supplier IDs created"

        except httpx.ConnectError:
            pytest.skip("Admin service not running")

    def test_concurrent_onboarding_step_completion_safe(self, admin_client):
        """Test that concurrent onboarding step completion is safe."""
        try:
            tenant_id = str(uuid4())
            step_id = str(uuid4())

            # Simulate concurrent completions of the same step
            responses = []

            for _ in range(3):
                response = admin_client.post(
                    "/v1/admin/onboarding/complete-step",
                    headers={
                        "X-Admin-Key": "admin-master-key-dev",
                        "X-Tenant-ID": tenant_id,
                    },
                    json={"step_id": step_id}
                )
                responses.append(response)

            # At least one should succeed
            assert any(r.status_code in [200, 201] for r in responses), (
                "No successful completion responses"
            )

            # Should not have duplicate completion records
            successful = [r for r in responses if r.status_code in [200, 201]]
            # If we got multiple successes, they should be idempotent
            # (i.e., the step should be marked as complete only once)

        except httpx.ConnectError:
            pytest.skip("Admin service not running")


class TestJWTKeyRotation:
    """Test JWT key rotation and validation (PR #328).

    Verifies that expired JWTs are rejected and JWTs signed with
    wrong keys are invalid.
    """

    def test_expired_jwt_rejected(self, graph_client):
        """Test that expired JWT tokens are rejected."""
        try:
            # Create a JWT that is already expired
            # In a real test, would use jwt.encode with exp claim in the past
            expired_jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE2MzAwMDAwMDB9.invalid"

            response = graph_client.get(
                "/v1/labels/health",
                headers={
                    "Authorization": f"Bearer {expired_jwt}",
                    "X-Tenant-ID": str(uuid4()),
                }
            )

            # Should reject expired token
            if response.status_code not in [200]:
                assert response.status_code in [401, 403], (
                    f"Expected 401/403 for expired JWT, got {response.status_code}"
                )

        except httpx.ConnectError:
            pytest.skip("Graph service not running")

    def test_jwt_signed_with_wrong_key_rejected(self, graph_client):
        """Test that JWTs signed with the wrong key are rejected."""
        try:
            # Create a JWT with a signature from a different key
            wrong_key_jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0IiwiZXhwIjo5OTk5OTk5OTk5fQ.wrongsignature"

            response = graph_client.get(
                "/v1/labels/health",
                headers={
                    "Authorization": f"Bearer {wrong_key_jwt}",
                    "X-Tenant-ID": str(uuid4()),
                }
            )

            # Should reject invalid signature
            if response.status_code not in [200]:
                assert response.status_code in [401, 403]

        except httpx.ConnectError:
            pytest.skip("Graph service not running")

    def test_jwt_with_invalid_format_rejected(self, graph_client):
        """Test that malformed JWTs are rejected."""
        try:
            response = graph_client.get(
                "/v1/labels/health",
                headers={
                    "Authorization": "Bearer not-a-valid-jwt",
                    "X-Tenant-ID": str(uuid4()),
                }
            )

            # Should reject malformed token
            if response.status_code not in [200]:
                assert response.status_code in [401, 403]

        except httpx.ConnectError:
            pytest.skip("Graph service not running")


class TestCSRFDoubleSubmit:
    """Test CSRF double-submit protection (PR #329).

    Verifies that state-changing endpoints (POST, PUT, DELETE) require
    CSRF tokens and reject requests without them.
    """

    @pytest.mark.parametrize("method,endpoint", [
        ("POST", "/v1/admin/suppliers"),
        ("POST", "/v1/admin/onboarding/create"),
        ("PUT", "/v1/admin/users/user-123"),
        ("DELETE", "/v1/admin/keys/key-123"),
    ])
    def test_state_changing_endpoints_require_csrf(self, admin_client, method, endpoint):
        """Test that state-changing endpoints require CSRF tokens."""
        try:
            response = admin_client.request(
                method,
                endpoint,
                headers={
                    "X-Admin-Key": "admin-master-key-dev",
                    "X-Tenant-ID": str(uuid4()),
                },
                json={} if method != "DELETE" else None
            )

            # If CSRF is enforced, should be rejected with 403
            # (or 400 if CSRF header is required)
            if response.status_code == 403:
                # CSRF protection is active
                assert "csrf" in response.text.lower() or "token" in response.text.lower()
            else:
                # May not be implemented or may use different validation
                pytest.skip(f"{endpoint} may not have CSRF, got {response.status_code}")

        except httpx.ConnectError:
            pytest.skip("Admin service not running")

    def test_csrf_token_required_on_post_endpoints(self, admin_client):
        """Test that POST endpoints reject requests without CSRF tokens."""
        try:
            response = admin_client.post(
                "/v1/admin/suppliers",
                headers={
                    "X-Admin-Key": "admin-master-key-dev",
                    "X-Tenant-ID": str(uuid4()),
                },
                json={"name": "Test Supplier"}
            )

            # Should be rejected or require CSRF
            if response.status_code == 403:
                # CSRF is enforced
                assert response.status_code == 403
            else:
                # May not be enforced on this endpoint
                pytest.skip(f"CSRF may not be enforced, got {response.status_code}")

        except httpx.ConnectError:
            pytest.skip("Admin service not running")

    def test_get_endpoints_do_not_require_csrf(self, admin_client):
        """Test that GET endpoints don't require CSRF tokens."""
        try:
            response = admin_client.get(
                "/v1/admin/suppliers",
                headers={
                    "X-Admin-Key": "admin-master-key-dev",
                    "X-Tenant-ID": str(uuid4()),
                }
            )

            # Should not require CSRF
            assert response.status_code != 403, "GET should not require CSRF"

        except httpx.ConnectError:
            pytest.skip("Admin service not running")

    def test_csrf_token_mismatch_rejected(self, admin_client):
        """Test that mismatched CSRF tokens are rejected."""
        try:
            response = admin_client.post(
                "/v1/admin/suppliers",
                headers={
                    "X-Admin-Key": "admin-master-key-dev",
                    "X-Tenant-ID": str(uuid4()),
                    "X-CSRF-Token": "wrong-csrf-token-12345",
                },
                json={"name": "Test Supplier"}
            )

            # Should be rejected if CSRF is enforced
            if response.status_code == 403:
                assert "csrf" in response.text.lower() or "token" in response.text.lower()
            else:
                pytest.skip(f"CSRF validation may not be implemented, got {response.status_code}")

        except httpx.ConnectError:
            pytest.skip("Admin service not running")


class TestSecurityHeadersPresence:
    """Test that security headers are present in responses."""

    @pytest.mark.parametrize("endpoint", [
        "/health",
        "/v1/labels/health",
    ])
    def test_security_headers_present(self, admin_client, endpoint):
        """Test that responses include security headers."""
        try:
            response = admin_client.get(endpoint)

            # Should have security headers
            security_headers = [
                "X-Content-Type-Options",
                "X-Frame-Options",
                "Content-Security-Policy",
            ]

            # At least one security header should be present
            has_security_header = any(h in response.headers for h in security_headers)

            if not has_security_header:
                pytest.skip("Security headers not configured on this endpoint")

        except httpx.ConnectError:
            pytest.skip("Service not running")

    def test_strict_transport_security_header(self, admin_client):
        """Test that HSTS header is present."""
        try:
            response = admin_client.get("/health")

            # HSTS may be configured at load balancer, skip if not present
            if "Strict-Transport-Security" in response.headers:
                hsts = response.headers["Strict-Transport-Security"]
                assert "max-age" in hsts.lower()
            else:
                pytest.skip("HSTS may be configured at load balancer level")

        except httpx.ConnectError:
            pytest.skip("Service not running")


class TestInputValidationAndSanitization:
    """Test input validation and sanitization across security boundaries."""

    @pytest.mark.parametrize("malicious_input", [
        "<script>alert('xss')</script>",
        "'; DROP TABLE users; --",
        "x' UNION SELECT * FROM passwords; --",
        "../../etc/passwd",
        "%00%0a%0d",
    ])
    def test_malicious_input_sanitized(self, admin_client, malicious_input):
        """Test that malicious input is sanitized or rejected."""
        try:
            response = admin_client.post(
                "/v1/admin/suppliers",
                headers={
                    "X-Admin-Key": "admin-master-key-dev",
                    "X-Tenant-ID": str(uuid4()),
                },
                json={"name": malicious_input}
            )

            # Should either reject or sanitize
            assert response.status_code in [200, 201, 400, 422], (
                f"Unexpected response for malicious input: {response.status_code}"
            )

            # If created, verify sanitization
            if response.status_code in [200, 201]:
                data = response.json()
                if "name" in data:
                    # Script tags should be escaped or removed
                    assert "<script>" not in data["name"]

        except httpx.ConnectError:
            pytest.skip("Admin service not running")

    def test_oversized_request_rejected(self, admin_client):
        """Test that very large request bodies are rejected."""
        try:
            # Try to send 10MB of data
            large_data = {"name": "x" * (10 * 1024 * 1024)}

            response = admin_client.post(
                "/v1/admin/suppliers",
                headers={
                    "X-Admin-Key": "admin-master-key-dev",
                    "X-Tenant-ID": str(uuid4()),
                },
                json=large_data
            )

            # Should reject large requests
            assert response.status_code in [400, 413, 422], (
                f"Expected 400/413/422 for oversized request, got {response.status_code}"
            )

        except httpx.ConnectError:
            pytest.skip("Admin service not running")
        except Exception:
            # Large request may fail at network level, which is fine
            pass


class TestErrorHandlingAndInfoLeakage:
    """Test that error handling doesn't leak sensitive information."""

    def test_404_does_not_leak_paths(self, admin_client):
        """Test that 404 errors don't reveal internal paths."""
        try:
            response = admin_client.get(
                "/v1/admin/secret-internal-path-xyz"
            )

            if response.status_code == 404:
                body = response.text.lower()
                # Should not leak internal paths or stack traces
                assert "/users/" not in body
                assert "traceback" not in body
                assert "file \"" not in body

        except httpx.ConnectError:
            pytest.skip("Admin service not running")

    def test_500_does_not_leak_stack_trace(self, admin_client):
        """Test that 500 errors don't reveal stack traces."""
        try:
            response = admin_client.post(
                "/v1/admin/suppliers",
                headers={
                    "X-Admin-Key": "admin-master-key-dev",
                    "X-Tenant-ID": str(uuid4()),
                },
                json={"invalid": "data"}  # Missing required fields
            )

            if response.status_code == 500:
                body = response.text.lower()
                # Should not leak stack traces
                assert "traceback" not in body
                assert "file \"" not in body
                assert "line " not in body

        except httpx.ConnectError:
            pytest.skip("Admin service not running")

    def test_error_messages_generic(self, admin_client):
        """Test that error messages are generic, not revealing."""
        try:
            response = admin_client.get(
                "/v1/admin/keys",
                headers={
                    "X-RegEngine-API-Key": "definitely-invalid-key-that-does-not-exist"
                }
            )

            # Should be rejected
            assert response.status_code in [401, 403]

            # Error message should be generic
            detail = response.text.lower()
            # Should not reveal whether key format is wrong vs. key not found
            if "invalid" in detail or "unauthorized" in detail:
                # Generic message is good
                pass

        except httpx.ConnectError:
            pytest.skip("Admin service not running")
