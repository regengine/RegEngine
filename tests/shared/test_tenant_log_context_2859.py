"""#2859: the tenant resolved by TenantContextMiddleware must reach log lines.

``merge_contextvars`` is now first in the configured structlog chain, so the
bindings made by CorrelationIdMiddleware and RequestIDMiddleware reach the
rendered line. Nothing performed the equivalent binding for ``tenant_id``:
``TenantContextMiddleware`` resolved the tenant, stored it on
``request.state.tenant_id``, seeded the RLS contextvar — and never told the
logger. Every line emitted while serving an authenticated request therefore
rendered ``"tenant_id": "unknown"``, which is what the issue reports and what
makes "which tenant was affected by this error" unanswerable.

These tests assert against the JSON the *production* processor chain actually
renders (captured off the stdlib root logger that
``structlog.stdlib.LoggerFactory`` feeds), not against a
``structlog.testing.capture_logs`` shim — ``capture_logs`` disables the
configured processors, so it would bypass the very chain whose behaviour is
under test.
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SERVICES_DIR = _REPO_ROOT / "services"
for _p in (_SERVICES_DIR, _REPO_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import structlog  # noqa: E402

# NOTE: FastAPI must be a MODULE-level name — with ``from __future__ import
# annotations`` a route's annotations resolve from the function's globals.
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

INTERNAL_SECRET = "internal-secret-for-2859"
HANDLER_EVENT = "handler_emitted_a_log_line_2859"


class _RenderedJsonCapture(logging.Handler):
    """Collect the JSON lines the configured structlog chain really emits."""

    def __init__(self) -> None:
        super().__init__()
        self.lines: list[dict] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            payload = json.loads(record.getMessage())
        except (ValueError, TypeError):
            return
        if isinstance(payload, dict):
            self.lines.append(payload)

    def events(self, name: str) -> list[dict]:
        return [line for line in self.lines if line.get("event") == name]


@pytest.fixture
def rendered_logs():
    """Capture rendered log lines, leaving global logging state as found."""
    # Importing the module installs the production structlog configuration.
    import shared.observability.context  # noqa: F401

    handler = _RenderedJsonCapture()
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    structlog.contextvars.clear_contextvars()
    try:
        yield handler
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)
        structlog.contextvars.clear_contextvars()


@pytest.fixture
def client(monkeypatch):
    """A protected route behind the real TenantContextMiddleware."""
    monkeypatch.setenv("REGENGINE_INTERNAL_SECRET", INTERNAL_SECRET)

    from shared.middleware.tenant_context import TenantContextMiddleware

    app = FastAPI()
    app.add_middleware(TenantContextMiddleware)
    log = structlog.get_logger("test_tenant_log_context_2859")

    @app.get("/api/v1/protected")
    def protected():
        log.info(HANDLER_EVENT)
        return {"ok": True}

    return TestClient(app)


def _tenant_headers(tenant_id: str) -> dict[str, str]:
    """Headers the middleware accepts as an internal, tenant-bearing call."""
    return {
        "X-RegEngine-Tenant-ID": tenant_id,
        "X-RegEngine-Internal-Secret": INTERNAL_SECRET,
    }


def test_resolved_tenant_reaches_the_log_line(client, rendered_logs):
    """The regression: a log line emitted while serving a request for a
    resolved tenant must carry that tenant, not the ``"unknown"`` placeholder.
    """
    tenant_id = str(uuid.uuid4())

    response = client.get("/api/v1/protected", headers=_tenant_headers(tenant_id))
    assert response.status_code == 200, response.text

    lines = rendered_logs.events(HANDLER_EVENT)
    assert lines, "handler log line was not captured — capture setup is broken"
    assert lines[0]["tenant_id"] == tenant_id, (
        "log line rendered tenant_id=%r while TenantContextMiddleware had "
        "resolved %r — the resolved tenant never reached the logger"
        % (lines[0].get("tenant_id"), tenant_id)
    )


def test_tenant_is_not_carried_into_a_later_request(client, rendered_logs):
    """One request's tenant must never appear on a later request's lines."""
    first_tenant = str(uuid.uuid4())
    second_tenant = str(uuid.uuid4())

    assert client.get("/api/v1/protected", headers=_tenant_headers(first_tenant)).status_code == 200
    assert client.get("/api/v1/protected", headers=_tenant_headers(second_tenant)).status_code == 200

    lines = rendered_logs.events(HANDLER_EVENT)
    assert len(lines) == 2, f"expected one line per request, captured {len(lines)}"
    assert lines[0]["tenant_id"] == first_tenant
    assert lines[1]["tenant_id"] == second_tenant, (
        "second request logged %r — the first request's tenant leaked forward"
        % (lines[1].get("tenant_id"),)
    )


def test_audit_field_present_as_unknown_when_no_tenant_resolves(client, rendered_logs):
    """With no tenant to bind, the audit field is still emitted as the
    documented ``"unknown"`` placeholder rather than being absent."""
    response = client.get("/api/v1/protected")
    assert response.status_code == 200, response.text

    lines = rendered_logs.events(HANDLER_EVENT)
    assert lines, "handler log line was not captured"
    assert lines[0]["tenant_id"] == "unknown"


def test_unbind_clears_both_context_mechanisms():
    """``unbind_tenant_log_context`` must clear the structlog binding *and*
    reset the raw ContextVar, or a worker thread would keep re-seeding a
    stale tenant from :func:`_capture_observability_context`."""
    from shared.observability.context import (
        _capture_observability_context,
        bind_tenant_log_context,
        unbind_tenant_log_context,
    )

    tenant_id = str(uuid.uuid4())
    structlog.contextvars.clear_contextvars()

    token = bind_tenant_log_context(tenant_id)
    try:
        assert structlog.contextvars.get_contextvars().get("tenant_id") == tenant_id
        # The raw ContextVar half — what background jobs inherit.
        assert _capture_observability_context()["tenant_id"] == tenant_id
    finally:
        unbind_tenant_log_context(token)

    assert "tenant_id" not in structlog.contextvars.get_contextvars()
    assert _capture_observability_context()["tenant_id"] == "unknown"
