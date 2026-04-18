"""Tenant-isolation regression tests for the EPCIS router (issue #1146).

These tests verify that the EPCIS endpoints:
1. Reject any request that supplies ``tenant_id`` as a query parameter
   (HTTP 403).
2. Derive the tenant exclusively from ``X-Tenant-ID`` / API-key lookup.

Prior to the #1146 fix, ``?tenant_id=<other>`` would override the authenticated
tenant and allow cross-tenant reads/writes.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Build a minimal FastAPI app wrapping only the EPCIS router.

    Overrides the ``_verify_api_key`` dependency so tests can focus on the
    tenant-isolation logic rather than auth wiring.
    """
    from app.epcis.router import router
    from app.webhook_compat import _verify_api_key

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    return TestClient(app)


# ---------------------------------------------------------------------------
# Query-param override is rejected
# ---------------------------------------------------------------------------


def _sample_event() -> dict:
    """Return a valid-ish EPCIS event so the router progresses past parsing."""
    return {
        "type": "ObjectEvent",
        "eventTime": "2026-04-17T12:00:00Z",
        "action": "OBSERVE",
        "bizStep": "shipping",
        "epcList": ["urn:epc:id:sgtin:0614141.107346.2017"],
    }


def test_ingest_event_rejects_tenant_query_override(client):
    """POST /events?tenant_id=victim must return 403 and not ingest."""
    resp = client.post(
        "/api/v1/epcis/events",
        params={"tenant_id": "victim-tenant"},
        headers={"X-Tenant-ID": "attacker-tenant"},
        json=_sample_event(),
    )
    assert resp.status_code == 403
    assert "tenant_id query parameter" in resp.json()["detail"]


def test_batch_ingest_rejects_tenant_query_override(client):
    resp = client.post(
        "/api/v1/epcis/events/batch",
        params={"tenant_id": "victim-tenant"},
        headers={"X-Tenant-ID": "attacker-tenant"},
        json={"events": [_sample_event()]},
    )
    assert resp.status_code == 403


def test_get_event_rejects_tenant_query_override(client):
    resp = client.get(
        "/api/v1/epcis/events/some-id",
        params={"tenant_id": "victim-tenant"},
        headers={"X-Tenant-ID": "attacker-tenant"},
    )
    assert resp.status_code == 403


def test_export_rejects_tenant_query_override(client):
    resp = client.get(
        "/api/v1/epcis/export",
        params={"tenant_id": "victim-tenant"},
        headers={"X-Tenant-ID": "attacker-tenant"},
    )
    assert resp.status_code == 403


def test_xml_ingest_rejects_tenant_query_override(client):
    resp = client.post(
        "/api/v1/epcis/events/xml",
        params={"tenant_id": "victim-tenant"},
        headers={"X-Tenant-ID": "attacker-tenant", "Content-Type": "application/xml"},
        content=b"<?xml version=\"1.0\"?><EPCISDocument/>",
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Resolver helper unit test
# ---------------------------------------------------------------------------


def test_resolve_authenticated_tenant_ignores_explicit_tenant():
    """_resolve_authenticated_tenant must never pass an explicit_tenant_id
    from the query string to resolve_tenant_id."""
    from unittest.mock import MagicMock
    from app.epcis import router as epcis_router

    captured = {}

    def fake_resolver(explicit_tenant_id, x_tenant_id, api_key):
        captured["explicit_tenant_id"] = explicit_tenant_id
        captured["x_tenant_id"] = x_tenant_id
        captured["api_key"] = api_key
        return x_tenant_id or "resolved-from-api-key"

    request = MagicMock()
    # No query params => helper should be happy, but the resolver still gets
    # explicit_tenant_id=None.
    request.query_params = {}

    with patch.object(epcis_router, "_resolve_tenant_id", side_effect=fake_resolver):
        tenant = epcis_router._resolve_authenticated_tenant(
            request=request,
            x_tenant_id="header-tenant",
            x_regengine_api_key="key-abc",
        )

    assert tenant == "header-tenant"
    assert captured["explicit_tenant_id"] is None


def test_reject_tenant_query_override_raises():
    from fastapi import HTTPException
    from unittest.mock import MagicMock
    from app.epcis.router import _reject_tenant_query_override

    request = MagicMock()
    request.query_params = {"tenant_id": "foo"}

    with pytest.raises(HTTPException) as exc:
        _reject_tenant_query_override(request)
    assert exc.value.status_code == 403
