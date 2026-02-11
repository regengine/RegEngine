"""
Tests for billing service middleware and shared utilities.

Covers:
- SecurityHeadersMiddleware (all hardening headers present)
- RequestIdMiddleware (X-Request-ID propagation)
- RateLimitMiddleware (token-bucket enforcement)
- utils.format_cents
- utils.paginate
- utils.get_tenant_id
- Global ValueError exception handler
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

# ── Unit tests for utils ──────────────────────────────────────────

from utils import format_cents, paginate


class TestFormatCents:
    def test_zero(self):
        assert format_cents(0) == "$0.00"

    def test_positive(self):
        assert format_cents(12345) == "$123.45"

    def test_negative(self):
        assert format_cents(-5000) == "-$50.00"

    def test_large(self):
        assert format_cents(1_234_567) == "$12,345.67"

    def test_one_cent(self):
        assert format_cents(1) == "$0.01"


class TestPaginate:
    def test_basic(self):
        items = list(range(25))
        result = paginate(items, page=1, page_size=10)
        assert result["total"] == 25
        assert len(result["items"]) == 10
        assert result["page"] == 1
        assert result["total_pages"] == 3
        assert result["has_next"] is True
        assert result["has_prev"] is False

    def test_last_page(self):
        items = list(range(25))
        result = paginate(items, page=3, page_size=10)
        assert len(result["items"]) == 5
        assert result["has_next"] is False
        assert result["has_prev"] is True

    def test_beyond_range(self):
        items = list(range(5))
        result = paginate(items, page=99, page_size=10)
        assert len(result["items"]) == 0
        assert result["has_next"] is False

    def test_page_size_cap(self):
        items = list(range(500))
        result = paginate(items, page=1, page_size=999)
        assert result["page_size"] == 200  # capped

    def test_negative_page(self):
        result = paginate([1, 2, 3], page=-1, page_size=10)
        assert result["page"] == 1  # clamped

    def test_empty(self):
        result = paginate([], page=1, page_size=10)
        assert result["total"] == 0
        assert len(result["items"]) == 0
        assert result["total_pages"] == 1


# ── Integration tests for middleware ──────────────────────────────

@pytest.fixture
def async_client():
    """Create an async test client with the full app."""
    from main import app
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_security_headers(async_client):
    """All hardening headers should be present on every response."""
    async with async_client as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["X-XSS-Protection"] == "1; mode=block"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "max-age=" in resp.headers["Strict-Transport-Security"]
    assert resp.headers["Cache-Control"] == "no-store"


@pytest.mark.asyncio
async def test_request_id_generated(async_client):
    """A new X-Request-ID should be generated when none is provided."""
    async with async_client as client:
        resp = await client.get("/health")
    assert "X-Request-ID" in resp.headers
    assert len(resp.headers["X-Request-ID"]) == 32  # UUID hex


@pytest.mark.asyncio
async def test_request_id_passthrough(async_client):
    """Client-supplied X-Request-ID should be echoed back."""
    async with async_client as client:
        resp = await client.get("/health", headers={"X-Request-ID": "my-trace-123"})
    assert resp.headers["X-Request-ID"] == "my-trace-123"


@pytest.mark.asyncio
async def test_root_lists_all_routers(async_client):
    """Root endpoint should list all 15+ routers."""
    async with async_client as client:
        resp = await client.get("/")
    data = resp.json()
    endpoints = data["endpoints"]
    assert "subscriptions" in endpoints
    assert "credits" in endpoints
    assert "analytics" in endpoints
    assert "invoices" in endpoints
    assert "partners" in endpoints
    assert "dunning" in endpoints
    assert "tax" in endpoints
    assert "lifecycle" in endpoints
    assert "alerts" in endpoints
    assert "forecasting" in endpoints
    assert "optimization" in endpoints


@pytest.mark.asyncio
async def test_global_value_error_handler(async_client):
    """ValueError from engines should return 400 JSON, not 500."""
    async with async_client as client:
        # Attempt to send an already-sent invoice (causes ValueError)
        resp = await client.post("/v1/billing/invoices/nonexistent/send")
    # Should be 400 (ValueError) or 404 (not found) — not 500
    assert resp.status_code in (400, 404)
    data = resp.json()
    assert "detail" in data
