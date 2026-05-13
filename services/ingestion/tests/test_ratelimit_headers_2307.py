"""Issue #2307 — ``X-RateLimit-*`` headers MUST be emitted on 2xx responses.

Historically rate-limit headers were only attached to 429 responses, which
forced clients to over-fetch before they could see budget metadata. The
ingestion service now mounts ``RateLimitHeadersMiddleware``, which mirrors
``request.state.rate_limit_*`` onto outbound 2xx responses on the
rate-limited path prefixes (``/api/v1/records``, ``/api/v1/webhooks``,
``/api/v1/fda/export``, ``/api/v1/ingest``).

This test runs the middleware against a minimal FastAPI app, plants the
state values exactly the way the production guards do, and asserts the
five headers land on a 200.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
if str(service_dir) not in sys.path:
    sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.middleware import RateLimitHeadersMiddleware


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RateLimitHeadersMiddleware)

    @app.get("/api/v1/records/sample")
    async def _records_sample(request: Request):
        # Simulate what app.authz._store_rate_limit_headers / the
        # webhook _store_rate_limit_state helper writes to request.state
        # immediately after consume_tenant_rate_limit() returns.
        request.state.rate_limit_limit = 120
        request.state.rate_limit_remaining = 117
        request.state.rate_limit_reset = "1715553600"
        request.state.rate_limit_tenant = "tenant-acme"
        request.state.rate_limit_scope = "rbac.records.read.admin"
        return {"ok": True}

    @app.get("/api/v1/webhooks/recent")
    async def _webhooks_recent(request: Request):
        request.state.rate_limit_limit = 30
        request.state.rate_limit_remaining = 29
        request.state.rate_limit_reset = "1715553600"
        request.state.rate_limit_tenant = "tenant-acme"
        request.state.rate_limit_scope = "webhooks.read.recent"
        return {"events": []}

    @app.get("/api/v1/fda/export/run")
    async def _fda_export(request: Request):
        request.state.rate_limit_limit = 10
        request.state.rate_limit_remaining = 9
        request.state.rate_limit_reset = "1715553600"
        request.state.rate_limit_tenant = "tenant-acme"
        request.state.rate_limit_scope = "fda.export"
        return {"status": "queued"}

    @app.get("/healthz")
    async def _healthz():
        # Unauthenticated route — middleware must not annotate it.
        return {"status": "ok"}

    @app.get("/api/v1/records/empty")
    async def _no_state():
        # Handler that forgot to populate request.state — middleware must
        # NOT invent values. (Defensive: no header should appear.)
        return {"ok": True}

    return app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(_build_app())


# ---------------------------------------------------------------------------
# Headers present on 2xx for each rate-limited prefix
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "path, expected_scope, expected_limit",
    [
        ("/api/v1/records/sample", "rbac.records.read.admin", "120"),
        ("/api/v1/webhooks/recent", "webhooks.read.recent", "30"),
        ("/api/v1/fda/export/run", "fda.export", "10"),
    ],
)
def test_rate_limit_headers_on_2xx(
    client: TestClient,
    path: str,
    expected_scope: str,
    expected_limit: str,
) -> None:
    resp = client.get(path)
    assert resp.status_code == 200, resp.text

    # Acceptance criterion: all five headers visible on a successful
    # response so strict clients can pre-emptively back off.
    assert resp.headers["X-RateLimit-Limit"] == expected_limit
    assert resp.headers["X-RateLimit-Remaining"]  # non-empty
    assert resp.headers["X-RateLimit-Reset"] == "1715553600"
    assert resp.headers["X-RateLimit-Tenant"] == "tenant-acme"
    assert resp.headers["X-RateLimit-Scope"] == expected_scope


# ---------------------------------------------------------------------------
# Negative cases — middleware must NOT leak misleading state.
# ---------------------------------------------------------------------------

def test_unauthenticated_route_has_no_ratelimit_headers(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert "X-RateLimit-Limit" not in resp.headers
    assert "X-RateLimit-Reset" not in resp.headers


def test_no_state_means_no_headers(client: TestClient) -> None:
    """If the handler did not record bucket state, do not fabricate one."""
    resp = client.get("/api/v1/records/empty")
    assert resp.status_code == 200
    assert "X-RateLimit-Limit" not in resp.headers
    assert "X-RateLimit-Scope" not in resp.headers


# ---------------------------------------------------------------------------
# Read-only contract: middleware does NOT call consume_tenant_rate_limit.
# ---------------------------------------------------------------------------

def test_middleware_does_not_consume_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-emitting headers must not double-count against the tenant bucket."""
    from shared import tenant_rate_limiting as trl

    calls = {"n": 0}
    real_consume = trl.consume_tenant_rate_limit

    def _spy(**kwargs):
        calls["n"] += 1
        return real_consume(**kwargs)

    monkeypatch.setattr(trl, "consume_tenant_rate_limit", _spy)

    client = TestClient(_build_app())
    resp = client.get("/api/v1/records/sample")
    assert resp.status_code == 200
    # Our app has no rate-limit guard wired (this is a unit harness), so
    # consume_tenant_rate_limit must NOT have been invoked by the
    # middleware itself.
    assert calls["n"] == 0
