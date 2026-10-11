"""Boundary and edge-case coverage for ``RateLimitHeadersMiddleware``.

Complements ``test_ratelimit_headers_2307.py`` (happy-path header emission).
Covers: slash-boundary prefix matching, non-2xx exclusion, handler-set
header precedence, zero/empty/partial state, per-request tenant isolation,
custom prefixes, and 429 passthrough.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
if str(service_dir) not in sys.path:
    sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from app.middleware import RateLimitHeadersMiddleware
from app.middleware.ratelimit_headers import _path_matches
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient


def _plant_state(request: Request, tenant: str = "tenant-acme", remaining: int = 117) -> None:
    request.state.rate_limit_limit = 120
    request.state.rate_limit_remaining = remaining
    request.state.rate_limit_reset = "1715553600"
    request.state.rate_limit_tenant = tenant
    request.state.rate_limit_scope = "rbac.records.read.admin"


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RateLimitHeadersMiddleware)

    @app.get("/api/v1/records/sample")
    async def _records_sample(request: Request):
        _plant_state(request)
        return {"ok": True}

    # String-prefix of a guarded prefix, but NOT slash-boundary guarded.
    @app.get("/api/v1/ingestion")
    async def _lookalike(request: Request):
        _plant_state(request)
        return {"ok": True}

    @app.get("/api/v1/records2")
    async def _lookalike2(request: Request):
        _plant_state(request)
        return {"ok": True}

    @app.get("/api/v1/records/explicit")
    async def _explicit(request: Request):
        _plant_state(request, remaining=117)
        return JSONResponse(
            content={"ok": True},
            headers={"X-RateLimit-Remaining": "42"},
        )

    @app.get("/api/v1/records/zero")
    async def _zero(request: Request):
        _plant_state(request, remaining=0)
        return {"ok": True}

    @app.get("/api/v1/records/partial")
    async def _partial(request: Request):
        request.state.rate_limit_limit = 120
        return {"ok": True}

    @app.get("/api/v1/records/empty-string")
    async def _empty_string(request: Request):
        request.state.rate_limit_limit = ""
        request.state.rate_limit_remaining = 5
        request.state.rate_limit_reset = "1715553600"
        request.state.rate_limit_tenant = "tenant-acme"
        request.state.rate_limit_scope = "s"
        return {"ok": True}

    @app.get("/api/v1/records/created")
    async def _created(request: Request):
        _plant_state(request)
        return JSONResponse(status_code=201, content={"ok": True})

    @app.get("/api/v1/records/failure")
    async def _failure(request: Request):
        _plant_state(request)
        return JSONResponse(status_code=400, content={"ok": False})

    @app.get("/api/v1/records/tenant-a")
    async def _tenant_a(request: Request):
        _plant_state(request, tenant="tenant-a")
        return {"ok": True}

    @app.get("/api/v1/records/tenant-b")
    async def _tenant_b(request: Request):
        _plant_state(request, tenant="tenant-b")
        return {"ok": True}

    return app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(_build_app())


# ---------------------------------------------------------------------------
# Prefix slash-boundary (regression: plain startswith matched too much)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path, expected",
    [
        ("/api/v1/ingest", True),
        ("/api/v1/ingest/", True),
        ("/api/v1/ingest/jobs", True),
        ("/api/v1/records", True),
        ("/api/v1/records/abc", True),
        ("/api/v1/webhooks", True),
        ("/api/v1/webhooks/recent", True),
        ("/api/v1/fda/export", True),
        ("/api/v1/fda/export/run", True),
        # String prefix without a slash boundary: NOT guarded.
        ("/api/v1/ingestion", False),
        ("/api/v1/ingestXYZ", False),
        ("/api/v1/records2", False),
        ("/api/v1/records-evil", False),
        ("/api/v1/webhooks2", False),
        ("/api/v1/fda/exporter", False),
        ("/healthz", False),
        ("/api/v1/other", False),
        ("", False),
    ],
)
def test_path_matches_requires_slash_boundary(path: str, expected: bool) -> None:
    prefixes = ("/api/v1/records", "/api/v1/webhooks", "/api/v1/fda/export", "/api/v1/ingest")
    assert _path_matches(path, prefixes) is expected


def test_lookalike_routes_get_no_headers(client: TestClient) -> None:
    """State planted on a non-guarded lookalike path must not be mirrored."""
    for path in ("/api/v1/ingestion", "/api/v1/records2"):
        resp = client.get(path)
        assert resp.status_code == 200, resp.text
        assert "X-RateLimit-Limit" not in resp.headers
        assert "X-RateLimit-Tenant" not in resp.headers


def test_exact_prefix_and_created_status_annotated(client: TestClient) -> None:
    resp = client.get("/api/v1/records/sample")
    assert resp.status_code == 200
    assert resp.headers["X-RateLimit-Limit"] == "120"

    resp = client.get("/api/v1/records/created")
    assert resp.status_code == 201
    assert resp.headers["X-RateLimit-Limit"] == "120"


# ---------------------------------------------------------------------------
# Status-code scope: only 2xx annotated
# ---------------------------------------------------------------------------


def test_non_2xx_gets_no_mirrored_headers(client: TestClient) -> None:
    resp = client.get("/api/v1/records/failure")
    assert resp.status_code == 400
    assert "X-RateLimit-Limit" not in resp.headers
    assert "X-RateLimit-Remaining" not in resp.headers
    assert "X-RateLimit-Tenant" not in resp.headers


# ---------------------------------------------------------------------------
# Handler-set values win; zero/empty/partial state handled
# ---------------------------------------------------------------------------


def test_handler_explicit_header_not_overwritten(client: TestClient) -> None:
    resp = client.get("/api/v1/records/explicit")
    assert resp.status_code == 200
    assert resp.headers["X-RateLimit-Remaining"] == "42"
    # Other headers still mirrored from state.
    assert resp.headers["X-RateLimit-Limit"] == "120"


def test_zero_remaining_is_emitted(client: TestClient) -> None:
    """A depleted-but-allowed budget (remaining=0) is real signal, not missing."""
    resp = client.get("/api/v1/records/zero")
    assert resp.status_code == 200
    assert resp.headers["X-RateLimit-Remaining"] == "0"


def test_empty_string_state_skipped(client: TestClient) -> None:
    resp = client.get("/api/v1/records/empty-string")
    assert resp.status_code == 200
    assert "X-RateLimit-Limit" not in resp.headers
    assert resp.headers["X-RateLimit-Remaining"] == "5"


def test_partial_state_emits_only_what_exists(client: TestClient) -> None:
    resp = client.get("/api/v1/records/partial")
    assert resp.status_code == 200
    assert resp.headers["X-RateLimit-Limit"] == "120"
    assert "X-RateLimit-Remaining" not in resp.headers
    assert "X-RateLimit-Tenant" not in resp.headers
    assert "X-RateLimit-Scope" not in resp.headers


# ---------------------------------------------------------------------------
# Tenant boundary: per-request state, no bleed between tenants
# ---------------------------------------------------------------------------


def test_tenant_headers_do_not_bleed_across_requests(client: TestClient) -> None:
    resp_a = client.get("/api/v1/records/tenant-a")
    resp_b = client.get("/api/v1/records/tenant-b")
    assert resp_a.headers["X-RateLimit-Tenant"] == "tenant-a"
    assert resp_b.headers["X-RateLimit-Tenant"] == "tenant-b"
    # Re-request A to prove B did not contaminate shared middleware state.
    resp_a2 = client.get("/api/v1/records/tenant-a")
    assert resp_a2.headers["X-RateLimit-Tenant"] == "tenant-a"


# ---------------------------------------------------------------------------
# Custom prefixes honored
# ---------------------------------------------------------------------------


def test_custom_prefixes() -> None:
    app = FastAPI()
    app.add_middleware(RateLimitHeadersMiddleware, prefixes=("/custom",))

    @app.get("/custom/thing")
    async def _custom(request: Request):
        _plant_state(request)
        return {"ok": True}

    @app.get("/api/v1/records/sample")
    async def _records(request: Request):
        _plant_state(request)
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/custom/thing").headers["X-RateLimit-Limit"] == "120"
    assert "X-RateLimit-Limit" not in client.get("/api/v1/records/sample").headers


# ---------------------------------------------------------------------------
# 429 path keeps its own headers untouched
# ---------------------------------------------------------------------------


def test_429_headers_preserved() -> None:
    app = FastAPI()
    app.add_middleware(RateLimitHeadersMiddleware)

    @app.get("/api/v1/records/guarded")
    async def _guarded(request: Request):
        from fastapi import HTTPException

        _plant_state(request, remaining=0)
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={
                "Retry-After": "60",
                "X-RateLimit-Limit": "120",
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": "1715553600",
                "X-RateLimit-Tenant": "tenant-acme",
                "X-RateLimit-Scope": "rbac",
            },
        )

    resp = TestClient(app).get("/api/v1/records/guarded")
    assert resp.status_code == 429
    assert resp.headers["X-RateLimit-Remaining"] == "0"
    assert resp.headers["Retry-After"] == "60"
