"""Tests for correlation-ID propagation across HTTP, structlog, Kafka (#1316/#1317/#1318).

Covers:
* CorrelationIdMiddleware honours inbound X-Correlation-ID header.
* CorrelationIdMiddleware mints a UUID when the header is absent.
* The mint is exposed on request.state, the contextvar, and structlog.
* structlog _inject_context includes correlation_id in every log record.
* Kafka propagation helpers round-trip the ID through headers.
* bind_correlation_context re-hydrates the contextvar in consumer handlers.
"""

from __future__ import annotations

import json
import logging

import pytest
import structlog
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient


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


# ---------------------------------------------------------------------------
# Kafka propagation (#1318)
# ---------------------------------------------------------------------------


def test_inject_correlation_headers_round_trip():
    from shared.observability.correlation import correlation_id_ctx
    from shared.observability.kafka_propagation import (
        extract_correlation_headers,
        inject_correlation_headers_tuples,
    )

    token = correlation_id_ctx.set("abc-123")
    try:
        headers = inject_correlation_headers_tuples()
    finally:
        correlation_id_ctx.reset(token)

    cid, tid = extract_correlation_headers(headers)
    assert cid == "abc-123"
    assert tid is None  # tenant_id wasn't bound


def test_inject_headers_preserves_existing_entries():
    from shared.observability.correlation import correlation_id_ctx
    from shared.observability.kafka_propagation import (
        inject_correlation_headers_tuples,
    )

    existing = [("X-Custom", b"keep-me")]
    token = correlation_id_ctx.set("cid-xyz")
    try:
        headers = inject_correlation_headers_tuples(existing=existing)
    finally:
        correlation_id_ctx.reset(token)

    names = [name for name, _ in headers]
    assert "X-Custom" in names
    assert "X-Correlation-ID" in names


def test_inject_headers_mints_when_no_context():
    """A producer running outside a request should still emit a trace ID."""
    from shared.observability.kafka_propagation import (
        extract_correlation_headers,
        inject_correlation_headers_tuples,
    )

    headers = inject_correlation_headers_tuples()
    cid, _ = extract_correlation_headers(headers)
    assert cid is not None
    assert len(cid) == 36


def test_inject_headers_can_suppress_mint():
    from shared.observability.kafka_propagation import (
        extract_correlation_headers,
        inject_correlation_headers_tuples,
    )

    headers = inject_correlation_headers_tuples(mint_if_missing=False)
    cid, _ = extract_correlation_headers(headers)
    assert cid is None


def test_bind_correlation_context_reseeds_contextvar():
    """Consumer-side: bind_correlation_context should set contextvar for handler."""
    from shared.observability.correlation import (
        correlation_id_ctx,
        get_correlation_id,
    )
    from shared.observability.kafka_propagation import bind_correlation_context

    assert correlation_id_ctx.get() is None
    headers = [("X-Correlation-ID", b"consumer-trace-42")]
    with bind_correlation_context(headers) as cid:
        assert cid == "consumer-trace-42"
        assert get_correlation_id() == "consumer-trace-42"

    # After the with block the contextvar is released.
    assert correlation_id_ctx.get() is None


def test_bind_correlation_context_mints_when_headers_empty():
    from shared.observability.correlation import get_correlation_id
    from shared.observability.kafka_propagation import bind_correlation_context

    with bind_correlation_context([]) as cid:
        assert cid is not None
        assert get_correlation_id() == cid


def test_bind_correlation_context_respects_mint_flag():
    from shared.observability.correlation import get_correlation_id
    from shared.observability.kafka_propagation import bind_correlation_context

    with bind_correlation_context([], mint_if_missing=False) as cid:
        assert cid is None
        assert get_correlation_id() is None


def test_extract_correlation_headers_handles_string_values():
    """Some Kafka test doubles return str while real clients return bytes. Handle both."""
    from shared.observability.kafka_propagation import extract_correlation_headers

    headers = [
        ("X-Correlation-ID", "str-value"),
        ("X-RegEngine-Tenant-ID", b"bytes-tenant"),
    ]
    cid, tid = extract_correlation_headers(headers)
    assert cid == "str-value"
    assert tid == "bytes-tenant"


# ---------------------------------------------------------------------------
# End-to-end: HTTP → produce → consume hydration
# ---------------------------------------------------------------------------


def test_request_to_producer_to_consumer_chain():
    """Full story: an HTTP request's correlation_id propagates into Kafka headers,
    and a simulated consumer can extract and restore it.
    """
    from shared.observability.correlation import (
        CorrelationIdMiddleware,
        get_correlation_id,
    )
    from shared.observability.kafka_propagation import (
        bind_correlation_context,
        inject_correlation_headers_tuples,
    )

    produced_headers: list = []

    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware)

    @app.post("/produce")
    async def produce() -> dict:
        # Simulate a producer inside the request handler
        produced_headers.extend(inject_correlation_headers_tuples())
        return {"status": "ok"}

    client = TestClient(app)
    resp = client.post("/produce", headers={"X-Correlation-ID": "e2e-trace-99"})
    assert resp.status_code == 200

    # Now simulate a downstream consumer reading the headers
    with bind_correlation_context(produced_headers) as cid:
        assert cid == "e2e-trace-99"
        assert get_correlation_id() == "e2e-trace-99"
