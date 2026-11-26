"""Tests for correlation-ID propagation across HTTP, structlog, Kafka (#1316/#1317/#1318).

Covers:
* CorrelationIdMiddleware honours inbound X-Correlation-ID header.
* CorrelationIdMiddleware mints a UUID when the header is absent.
* The mint is exposed on request.state, the contextvar, and structlog.
* structlog _inject_context includes correlation_id in every log record.
* Kafka propagation helpers round-trip the ID through headers.
* bind_correlation_context re-hydrates the contextvar in consumer handlers.

Isolation contract: these tests assert on the DEFAULT state of the
correlation/tenant contextvars (e.g. "correlation_id is unset outside a
request"), so they are only meaningful from a clean slate. The autouse
``_clean_observability_context`` fixture below establishes that slate per
test and restores whatever state existed before, making this file
order-independent. Any test elsewhere that seeds these contextvars in the
main pytest thread must reset them (see the fixture in
services/scheduler/tests/test_correlation_propagation_1329.py, the
polluter that originally broke this file).
"""

from __future__ import annotations

import pytest
import structlog
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clean_observability_context():
    """Start each test from default contextvar state; restore on exit."""
    from shared.observability import context as obs_context
    from shared.observability.correlation import correlation_id_ctx

    saved_structlog = dict(structlog.contextvars.get_contextvars())
    structlog.contextvars.clear_contextvars()
    cid_token = correlation_id_ctx.set(None)
    tenant_token = obs_context._tenant_id_ctx.set("unknown")
    request_token = obs_context._request_id_ctx.set("unknown")
    try:
        yield
    finally:
        correlation_id_ctx.reset(cid_token)
        obs_context._tenant_id_ctx.reset(tenant_token)
        obs_context._request_id_ctx.reset(request_token)
        structlog.contextvars.clear_contextvars()
        if saved_structlog:
            structlog.contextvars.bind_contextvars(**saved_structlog)


# ---------------------------------------------------------------------------
# HTTP middleware
# ---------------------------------------------------------------------------


def _make_app_with_correlation():
    """Build a minimal FastAPI app wearing CorrelationIdMiddleware."""
    from shared.observability.correlation import (
        CorrelationIdMiddleware,
        get_correlation_id,
    )

    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/cid")
    async def handler(request: Request) -> dict:
        return {
            "state": request.state.correlation_id,
            "ctxvar": get_correlation_id(),
        }

    return app


def test_correlation_middleware_honours_inbound_header():
    app = _make_app_with_correlation()
    client = TestClient(app)

    resp = client.get("/cid", headers={"X-Correlation-ID": "caller-supplied-42"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "caller-supplied-42"
    assert body["ctxvar"] == "caller-supplied-42"
    assert resp.headers["X-Correlation-ID"] == "caller-supplied-42"


def test_correlation_middleware_mints_when_missing():
    app = _make_app_with_correlation()
    client = TestClient(app)

    resp = client.get("/cid")
    assert resp.status_code == 200
    body = resp.json()
    # UUID4 is 36 chars with dashes
    assert body["state"] == body["ctxvar"]
    assert len(body["state"]) == 36
    assert resp.headers["X-Correlation-ID"] == body["state"]


def test_correlation_caps_length_to_prevent_header_abuse():
    """A caller can't supply a 100kB correlation header (#1316)."""
    app = _make_app_with_correlation()
    client = TestClient(app)

    huge = "a" * 4096
    resp = client.get("/cid", headers={"X-Correlation-ID": huge})
    assert resp.status_code == 200
    assert len(resp.json()["state"]) == 128


def test_correlation_resets_between_requests():
    """Second request gets its own ID — contextvar isn't leaking."""
    app = _make_app_with_correlation()
    client = TestClient(app)

    resp1 = client.get("/cid", headers={"X-Correlation-ID": "first"})
    resp2 = client.get("/cid", headers={"X-Correlation-ID": "second"})
    assert resp1.json()["state"] == "first"
    assert resp2.json()["state"] == "second"


# ---------------------------------------------------------------------------
# Structlog injection (#1317)
# ---------------------------------------------------------------------------


def test_log_inject_context_includes_correlation_id():
    from shared.observability.correlation import correlation_id_ctx
    from shared.observability.log_config import _inject_context

    token = correlation_id_ctx.set("test-cid-abc")
    try:
        event = _inject_context(None, "info", {"event": "hello"})
    finally:
        correlation_id_ctx.reset(token)

    assert event["correlation_id"] == "test-cid-abc"


def test_log_inject_context_omits_correlation_id_when_unset():
    from shared.observability.log_config import _inject_context

    event = _inject_context(None, "info", {"event": "hello"})
    assert "correlation_id" not in event
