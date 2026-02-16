"""
Tests for per-tenant rate limiting middleware.

Tests the TenantRateLimitMiddleware and _InMemoryBucket.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from starlette.testclient import TestClient
from fastapi import FastAPI
from services.shared.tenant_rate_limiting import (
    TenantRateLimitMiddleware,
    _InMemoryBucket,
)


# ── Bucket Tests ────────────────────────────────────────────────

class TestInMemoryBucket:
    """Unit tests for the sliding-window bucket."""

    def test_allows_under_limit(self):
        bucket = _InMemoryBucket()
        allowed, remaining = bucket.is_allowed("t1", limit=5)
        assert allowed is True
        assert remaining == 4

    def test_blocks_at_limit(self):
        bucket = _InMemoryBucket()
        for _ in range(10):
            bucket.is_allowed("t2", limit=10)
        allowed, remaining = bucket.is_allowed("t2", limit=10)
        assert allowed is False
        assert remaining == 0

    def test_independent_keys(self):
        bucket = _InMemoryBucket()
        for _ in range(5):
            bucket.is_allowed("tenant-a", limit=5)
        # tenant-a is exhausted
        allowed_a, _ = bucket.is_allowed("tenant-a", limit=5)
        assert allowed_a is False
        # tenant-b should still be fine
        allowed_b, remaining_b = bucket.is_allowed("tenant-b", limit=5)
        assert allowed_b is True
        assert remaining_b == 4

    def test_remaining_decrements(self):
        bucket = _InMemoryBucket()
        for i in range(3):
            _, remaining = bucket.is_allowed("t3", limit=5)
            assert remaining == 5 - (i + 1)


# ── Middleware Integration Tests ────────────────────────────────

def _create_test_app(default_rpm: int = 5, tenant_overrides: dict = None) -> FastAPI:
    """Create a FastAPI app with tenant rate limiting for testing."""
    app = FastAPI()

    app.add_middleware(
        TenantRateLimitMiddleware,
        default_rpm=default_rpm,
        tenant_overrides=tenant_overrides or {},
    )

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/data")
    async def data():
        return {"data": "value"}

    return app


class TestTenantRateLimitMiddleware:
    """Integration tests for the middleware with a real FastAPI app."""

    def test_health_exempt(self):
        app = _create_test_app(default_rpm=1)
        client = TestClient(app)
        # Health should never be rate limited
        for _ in range(10):
            resp = client.get("/health")
            assert resp.status_code == 200

    def test_rate_limit_by_tenant(self):
        app = _create_test_app(default_rpm=3)
        client = TestClient(app)

        # First 3 should pass
        for i in range(3):
            resp = client.get("/api/data", headers={"X-Tenant-ID": "test-tenant"})
            assert resp.status_code == 200
            assert "X-RateLimit-Limit" in resp.headers
            assert resp.headers["X-RateLimit-Tenant"] == "test-tenant"

        # 4th should be blocked
        resp = client.get("/api/data", headers={"X-Tenant-ID": "test-tenant"})
        assert resp.status_code == 429
        assert "rate_limit_exceeded" in resp.json()["error"]

    def test_different_tenants_independent(self):
        app = _create_test_app(default_rpm=2)
        client = TestClient(app)

        # Exhaust tenant-a
        for _ in range(2):
            client.get("/api/data", headers={"X-Tenant-ID": "tenant-a"})

        # tenant-a blocked
        resp = client.get("/api/data", headers={"X-Tenant-ID": "tenant-a"})
        assert resp.status_code == 429

        # tenant-b unaffected
        resp = client.get("/api/data", headers={"X-Tenant-ID": "tenant-b"})
        assert resp.status_code == 200

    def test_tenant_override_higher_limit(self):
        app = _create_test_app(default_rpm=2, tenant_overrides={"premium": 10})
        client = TestClient(app)

        # Premium tenant gets 10 RPM
        for _ in range(5):
            resp = client.get("/api/data", headers={"X-Tenant-ID": "premium"})
            assert resp.status_code == 200

    def test_rate_limit_headers(self):
        app = _create_test_app(default_rpm=5)
        client = TestClient(app)
        resp = client.get("/api/data", headers={"X-Tenant-ID": "metrics-tenant"})
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == "5"
        assert int(resp.headers["X-RateLimit-Remaining"]) == 4
        assert resp.headers["X-RateLimit-Tenant"] == "metrics-tenant"

    def test_no_tenant_falls_back_to_ip(self):
        app = _create_test_app(default_rpm=3)
        client = TestClient(app)
        # Without X-Tenant-ID, falls back to IP-based
        for _ in range(3):
            resp = client.get("/api/data")
            assert resp.status_code == 200
        resp = client.get("/api/data")
        assert resp.status_code == 429
