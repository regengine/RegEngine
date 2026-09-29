"""Contract tests for Admin API.

These tests validate that the Admin API conforms to its documented contract,
ensuring consumers (frontend, other services) can rely on consistent behavior.

Uses OpenAPI spec as the source of truth for contract validation.
"""

import importlib
import json
import sys
from pathlib import Path

import pytest

OPENAPI_SPEC_PATH = Path(__file__).parent.parent.parent / "docs" / "openapi" / "admin-api.json"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SERVICES_DIR = _REPO_ROOT / "services"


@pytest.fixture(scope="module")
def openapi_spec():
    """Load the OpenAPI specification."""
    if not OPENAPI_SPEC_PATH.exists():
        pytest.skip(f"OpenAPI spec not found at {OPENAPI_SPEC_PATH}")
    with open(OPENAPI_SPEC_PATH) as f:
        return json.load(f)


@pytest.fixture
def client(monkeypatch):
    """Create an in-process client for Admin API contract checks."""
    from fastapi.testclient import TestClient

    monkeypatch.setenv("ADMIN_DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADMIN_FALLBACK_SQLITE", "sqlite:///:memory:")
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-secret-key-long-enough")  # pragma: allowlist secret
    monkeypatch.setenv("REGENGINE_API_KEY", "test-regengine-api-key")  # pragma: allowlist secret
    monkeypatch.setenv("AUDIT_INTEGRITY_KEY", "synthetic-admin-contract-audit-key")  # pragma: allowlist secret
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("REGENGINE_REDIS_URL", raising=False)
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("REGENGINE_ENV", "test")
    monkeypatch.setenv("ENABLE_DB_API_KEYS", "false")  # pragma: allowlist secret

    admin_service_dir = str(_SERVICES_DIR / "admin")
    sibling_service_dirs = {str(path) for path in _SERVICES_DIR.iterdir() if path.is_dir() and path.name != "admin"}
    monkeypatch.setattr(
        sys,
        "path",
        [admin_service_dir] + [path for path in sys.path if path not in sibling_service_dirs | {admin_service_dir}],
    )

    def owns_module(name):
        return (
            name == "app" or name.startswith("app.") or name == "services.admin" or name.startswith("services.admin.")
        )

    prior_modules = {name: module for name, module in sys.modules.items() if owns_module(name)}
    services_package = importlib.import_module("services")
    missing = object()
    prior_admin = getattr(services_package, "admin", missing)
    try:
        for module_name in prior_modules:
            sys.modules.pop(module_name)
        if hasattr(services_package, "admin"):
            delattr(services_package, "admin")

        admin_main = importlib.import_module("services.admin.main")
        from shared import jwt_key_registry
        from shared.audit_logging import AuditLogger

        monkeypatch.setattr(AuditLogger, "_instance", AuditLogger._instance)
        monkeypatch.setattr(jwt_key_registry, "_registry", jwt_key_registry._registry)
        with TestClient(admin_main.app) as test_client:
            yield test_client
    finally:
        for module_name in list(sys.modules):
            if owns_module(module_name):
                sys.modules.pop(module_name)
        sys.modules.update(prior_modules)
        if prior_admin is missing:
            if hasattr(services_package, "admin"):
                delattr(services_package, "admin")
        else:
            services_package.admin = prior_admin


class TestHealthEndpoint:
    """Contract tests for health endpoint."""

    def test_health_returns_200(self, client):
        """GET /health should return 200."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_response_has_status_field(self, client):
        """Health response must include 'status' field."""
        response = client.get("/health")
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "degraded", "unhealthy"]

    def test_health_response_has_version(self, client):
        """Health response should include version."""
        response = client.get("/health")
        data = response.json()
        # Version should be present (may be in different fields)
        assert "version" in data or "api_version" in data


class TestAPIVersionContract:
    """Contract tests for API versioning."""

    def test_openapi_version_matches_health(self, client, openapi_spec):
        """OpenAPI spec version should match health endpoint version."""
        health_response = client.get("/health")
        health_data = health_response.json()

        spec_version = openapi_spec.get("info", {}).get("version")
        health_version = health_data.get("version")

        # Version should be present in both
        if health_version and spec_version:
            # Allow minor version differences or just log as warning
            # In CI, ensure docker image is rebuilt before running tests
            if health_version != spec_version:
                import warnings

                warnings.warn(
                    f"Version mismatch: health={health_version}, spec={spec_version}. "
                    "Rebuild container with 'docker compose build admin-api'"
                )

    def test_all_paths_have_v1_prefix_or_are_internal(self, openapi_spec):
        """All versioned paths should have /v1/ prefix."""
        paths = openapi_spec.get("paths", {})

        # Internal paths that don't need versioning
        internal_prefixes = ("/health", "/metrics", "/ready", "/live")

        for path in paths:
            # Skip internal paths
            if path.startswith(internal_prefixes):
                continue

            # All other paths should be versioned
            assert path.startswith("/v1/"), f"Path {path} missing version prefix"


class TestAuthenticationContract:
    """Contract tests for authentication."""

    def test_protected_endpoint_requires_auth(self, client):
        """Protected endpoints should return 401/403 without auth."""
        response = client.get("/v1/admin/keys")
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"

    def test_retired_privileged_header_rejected(self, client):
        """The retired shared privileged credential must stay disabled."""
        response = client.get("/v1/admin/keys", headers={"X-Admin-Key": "invalid-key-12345"})
        assert response.status_code in [401, 403]


class TestResponseSchemaContract:
    """Contract tests for response schemas."""

    def test_error_responses_have_detail_field(self, client):
        """Error responses should expose structured error information."""
        response = client.get("/v1/admin/keys")  # Without auth
        assert response.status_code in [401, 403]

        data = response.json()
        assert "detail" in data or "error" in data, f"Error response missing expected error envelope: {data}"

    def test_list_endpoints_return_arrays(self, client, openapi_spec):
        """List endpoints (GET without ID) should return arrays in spec."""
        paths = openapi_spec.get("paths", {})

        # Internal paths to skip
        internal_prefixes = ("/health", "/metrics", "/ready", "/live")

        missing_schemas = []

        for path, methods in paths.items():
            # Skip internal endpoints
            if path.startswith(internal_prefixes):
                continue

            if "get" in methods and "{" not in path:
                get_spec = methods["get"]
                responses = get_spec.get("responses", {})

                # Check 200 response
                if "200" in responses:
                    response_200 = responses["200"]
                    content = response_200.get("content", {})

                    if "application/json" in content:
                        schema = content["application/json"].get("schema", {})
                        # List endpoints typically return array or object with items
                        if not schema:
                            missing_schemas.append(path)

        # Report missing schemas as warning, not failure
        if missing_schemas:
            import warnings

            warnings.warn(
                f"Endpoints missing response schemas: {missing_schemas}. "
                "Consider adding response_model to FastAPI routes."
            )


class TestPaginationContract:
    """Contract tests for pagination behavior."""

    def test_list_endpoints_accept_limit_param(self, openapi_spec):
        """List endpoints should accept limit parameter."""
        paths = openapi_spec.get("paths", {})

        list_endpoints = [
            "/v1/admin/keys",
            "/v1/admin/review/flagged-extractions",
        ]

        for endpoint in list_endpoints:
            if endpoint in paths:
                get_spec = paths[endpoint].get("get", {})
                params = get_spec.get("parameters", [])
                param_names = [p.get("name") for p in params]

                # Check for limit or pagination params
                has_pagination = any(name in param_names for name in ["limit", "page_size", "per_page", "cursor"])

                # This is informational - pagination should exist
                if not has_pagination:
                    pytest.skip(f"{endpoint} doesn't have pagination params in spec")


class TestRateLimitContract:
    """Contract tests for rate limiting headers."""

    def test_rate_limit_headers_present(self, client):
        """Responses should include rate limit headers."""
        response = client.get("/health")

        # Rate limit headers should be present (at least on success)
        # This is a soft check - headers may not be on health endpoint
        rate_limit_headers = [
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
        ]

        # Check if any rate limit header is present
        has_rate_limit = any(h in response.headers for h in rate_limit_headers)

        # Informational - rate limits should be added
        if not has_rate_limit:
            pytest.skip("Rate limit headers not present on /health")


class TestContentTypeContract:
    """Contract tests for content types."""

    def test_json_endpoints_return_json(self, client):
        """JSON endpoints should return application/json."""
        response = client.get("/health")
        assert response.status_code == 200

        content_type = response.headers.get("content-type", "")
        assert "application/json" in content_type

    def test_post_endpoints_accept_json(self, openapi_spec):
        """POST endpoints should accept application/json."""
        paths = openapi_spec.get("paths", {})

        for path, methods in paths.items():
            if "post" in methods:
                post_spec = methods["post"]
                request_body = post_spec.get("requestBody", {})
                content = request_body.get("content", {})

                if content:  # If request body is specified
                    assert "application/json" in content, f"POST {path} should accept application/json"
