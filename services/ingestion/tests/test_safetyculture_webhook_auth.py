"""SafetyCulture webhook authentication: fail closed, no data echo.

Covers the HIGH audit finding: the inbound webhook accepted calls
without a signature (``if secret and signature`` skipped verification
when either was missing) and returned the tenant's normalized
inspection record to the caller.

Contract under test:
* missing webhook secret on the connector -> 401 with a clear error
* missing signature header -> 401
* invalid signature -> 401
* valid signature -> 200 with only an accepted count, never the
  inspection data
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

# Make services/ingestion importable (same pattern as
# test_integration_router_1342.py).
service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app import integration_router  # noqa: E402
from app.webhook_compat import _verify_api_key, require_tenant_context  # noqa: E402
from shared.external_connectors import registry as registry_mod  # noqa: E402
from shared.external_connectors.base import ConnectorConfig  # noqa: E402
from shared.external_connectors.safetyculture import SafetyCultureConnector  # noqa: E402
from shared.tenant_context import TenantContext  # noqa: E402

TENANT = "tenant-sc-webhook"
CONNECTOR_ID = "safetyculture"
SECRET = "test-webhook-secret"

PAYLOAD = {"event_type": "AUDIT_COMPLETED", "audit_id": "audit-123"}


def _config(secret: str = SECRET) -> ConnectorConfig:
    return ConnectorConfig(
        connector_id=CONNECTOR_ID,
        display_name="SafetyCulture",
        category="food_safety",
        api_key="tenant-api-key",
        webhook_secret=secret,
        tenant_id=TENANT,
    )


def _sign(body: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _connector(secret: str = SECRET) -> SafetyCultureConnector:
    connector = SafetyCultureConnector(_config(secret))
    # Webhook handling fetches the full audit with the tenant's key
    # after auth. Stub the network call so tests never leave the box.
    connector._fetch_audit_detail = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "audit_id": "audit-123",
            "template_id": "tpl-1",
            "audit_title": "Receiving inspection",
            "completed_at": "2026-01-01T00:00:00Z",
            "audit_data": {"name": "Receiving inspection"},
        }
    )
    return connector


# ---------------------------------------------------------------------------
# Connector level: fail-closed signature checks
# ---------------------------------------------------------------------------


async def test_missing_secret_rejected():
    connector = _connector(secret="")
    body = json.dumps(PAYLOAD).encode()
    with pytest.raises(ValueError, match="not configured"):
        await connector.handle_webhook(body, {"x-sc-signature": _sign(body, SECRET)})
    # An unsigned caller must never trigger a fetch with the tenant key.
    connector._fetch_audit_detail.assert_not_awaited()


async def test_missing_signature_rejected():
    connector = _connector()
    with pytest.raises(ValueError, match="Missing.*signature"):
        await connector.handle_webhook(json.dumps(PAYLOAD).encode(), {})
    connector._fetch_audit_detail.assert_not_awaited()


async def test_blank_secret_rejected_as_not_configured():
    connector = _connector(secret="   ")
    body = json.dumps(PAYLOAD).encode()
    with pytest.raises(ValueError, match="not configured"):
        await connector.handle_webhook(body, {"x-sc-signature": _sign(body, SECRET)})
    # A blank secret is the same as no secret: never fetch with the tenant key.
    connector._fetch_audit_detail.assert_not_awaited()


async def test_bad_signature_rejected():
    connector = _connector()
    body = json.dumps(PAYLOAD).encode()
    with pytest.raises(ValueError, match="Invalid.*signature"):
        await connector.handle_webhook(body, {"x-sc-signature": "0" * 64})
    connector._fetch_audit_detail.assert_not_awaited()


async def test_valid_signature_accepted():
    connector = _connector()
    body = json.dumps(PAYLOAD).encode()
    events = await connector.handle_webhook(body, {"x-sc-signature": _sign(body)})
    assert len(events) == 1
    assert events[0].source_event_id == "audit-123"


async def test_valid_signature_with_prefix_accepted():
    connector = _connector()
    body = json.dumps(PAYLOAD).encode()
    events = await connector.handle_webhook(body, {"X-Sc-Signature": "sha256=" + _sign(body)})
    assert len(events) == 1


async def test_safetyculture_signature_header_accepted():
    connector = _connector()
    body = json.dumps(PAYLOAD).encode()
    events = await connector.handle_webhook(
        body, {"X-Safetyculture-Signature": _sign(body)}
    )
    assert len(events) == 1


async def test_safetyculture_signature_header_rejected_when_bad():
    connector = _connector()
    body = json.dumps(PAYLOAD).encode()
    with pytest.raises(ValueError, match="Invalid.*signature"):
        await connector.handle_webhook(
            body, {"X-Safetyculture-Signature": "0" * 64}
        )
    connector._fetch_audit_detail.assert_not_awaited()


# ---------------------------------------------------------------------------
# Documented provider shape: nested event types and resource ids
# ---------------------------------------------------------------------------

NESTED_PAYLOAD = {
    "event": {"event_types": ["TRIGGER_EVENT_INSPECTION_COMPLETED_STATUS"]},
    "resource": {"id": "audit-456"},
}

NESTED_DETAILS_PAYLOAD = {
    "event": {"event_types": "TRIGGER_EVENT_INSPECTION_COMPLETED"},
    "data": {"details": {"inspection_id": "audit-789"}},
}


async def test_nested_completion_shape_accepted_with_resource_id():
    connector = _connector()
    body = json.dumps(NESTED_PAYLOAD).encode()
    events = await connector.handle_webhook(body, {"x-sc-signature": _sign(body)})
    assert len(events) == 1
    connector._fetch_audit_detail.assert_awaited_once_with("audit-456")


async def test_nested_completion_shape_accepted_with_details_id():
    connector = _connector()
    body = json.dumps(NESTED_DETAILS_PAYLOAD).encode()
    events = await connector.handle_webhook(body, {"x-sc-signature": _sign(body)})
    assert len(events) == 1
    connector._fetch_audit_detail.assert_awaited_once_with("audit-789")


async def test_nested_non_completion_shape_ignored_without_fetch():
    connector = _connector()
    body = json.dumps(
        {"event": {"event_types": ["TRIGGER_EVENT_INSPECTION_UPDATED"]}}
    ).encode()
    events = await connector.handle_webhook(body, {"x-sc-signature": _sign(body)})
    assert events == []
    connector._fetch_audit_detail.assert_not_awaited()


async def test_nested_completion_without_id_ignored_without_fetch():
    connector = _connector()
    body = json.dumps(
        {"event": {"event_types": ["TRIGGER_EVENT_INSPECTION_COMPLETED_STATUS"]}}
    ).encode()
    events = await connector.handle_webhook(body, {"x-sc-signature": _sign(body)})
    assert events == []
    connector._fetch_audit_detail.assert_not_awaited()


async def test_nested_shape_missing_signature_rejected():
    connector = _connector()
    with pytest.raises(ValueError, match="Missing.*signature"):
        await connector.handle_webhook(json.dumps(NESTED_PAYLOAD).encode(), {})
    connector._fetch_audit_detail.assert_not_awaited()


async def test_nested_shape_bad_signature_rejected():
    connector = _connector()
    body = json.dumps(NESTED_PAYLOAD).encode()
    with pytest.raises(ValueError, match="Invalid.*signature"):
        await connector.handle_webhook(body, {"x-sc-signature": "0" * 64})
    connector._fetch_audit_detail.assert_not_awaited()


# ---------------------------------------------------------------------------
# Router level: 401 mapping and count-only responses
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(integration_router.router)

    async def _noop():
        return None

    async def _tenant_ctx(request: Request) -> TenantContext:
        return TenantContext(
            tenant_id=request.path_params.get("tenant_id", TENANT),
            principal_kind="test",
            principal_id="sc-webhook-test",
        )

    app.dependency_overrides[_verify_api_key] = _noop
    app.dependency_overrides[require_tenant_context] = _tenant_ctx
    return TestClient(app)


# The router answers every verification failure with one uniform 401 body,
# so a caller cannot tell a missing secret from a missing signature.
_UNIFORM_REJECTION = {"error": "webhook_rejected", "message": "Webhook verification failed"}


def _post(client: TestClient, body: bytes, headers: Dict[str, str] | None = None):
    return client.post(
        f"/api/v1/integrations/webhook/{TENANT}/{CONNECTOR_ID}",
        content=body,
        headers={"Content-Type": "application/json", **(headers or {})},
    )


def test_router_missing_signature_returns_401(client, monkeypatch):
    monkeypatch.setattr(registry_mod, "get_tenant_connectors", lambda _tid: {CONNECTOR_ID: _connector()})
    resp = _post(client, json.dumps(PAYLOAD).encode())
    assert resp.status_code == 401
    assert resp.json()["detail"] == _UNIFORM_REJECTION


def test_router_bad_signature_returns_401(client, monkeypatch):
    monkeypatch.setattr(registry_mod, "get_tenant_connectors", lambda _tid: {CONNECTOR_ID: _connector()})
    body = json.dumps(PAYLOAD).encode()
    resp = _post(client, body, {"X-Sc-Signature": "0" * 64})
    assert resp.status_code == 401


def test_router_missing_secret_returns_401(client, monkeypatch):
    connector = _connector(secret="")
    monkeypatch.setattr(registry_mod, "get_tenant_connectors", lambda _tid: {CONNECTOR_ID: connector})
    body = json.dumps(PAYLOAD).encode()
    resp = _post(client, body, {"X-Sc-Signature": _sign(body)})
    assert resp.status_code == 401
    assert resp.json()["detail"] == _UNIFORM_REJECTION


def test_router_valid_signature_returns_count_only(client, monkeypatch):
    monkeypatch.setattr(registry_mod, "get_tenant_connectors", lambda _tid: {CONNECTOR_ID: _connector()})
    body = json.dumps(PAYLOAD).encode()
    resp = _post(client, body, {"X-Sc-Signature": _sign(body)})
    assert resp.status_code == 200
    result: Dict[str, Any] = resp.json()
    assert result["accepted"] == 1
    # No inspection data may leak back to the webhook caller.
    assert "events" not in result
    assert "audit-123" not in resp.text


def test_router_nested_shape_returns_count_only(client, monkeypatch):
    monkeypatch.setattr(registry_mod, "get_tenant_connectors", lambda _tid: {CONNECTOR_ID: _connector()})
    body = json.dumps(NESTED_PAYLOAD).encode()
    resp = _post(client, body, {"X-Sc-Signature": _sign(body)})
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 1


def test_router_nested_shape_missing_signature_returns_401(client, monkeypatch):
    monkeypatch.setattr(registry_mod, "get_tenant_connectors", lambda _tid: {CONNECTOR_ID: _connector()})
    resp = _post(client, json.dumps(NESTED_PAYLOAD).encode())
    assert resp.status_code == 401
    assert resp.json()["detail"] == _UNIFORM_REJECTION


def test_reconfigure_rotates_webhook_secret(client, monkeypatch):
    """A second configure call must replace the cached connector.

    Otherwise a rotated webhook secret never takes effect and the old
    secret keeps authorizing fetches with the tenant key.
    """
    from shared.external_connectors.safetyculture import SafetyCultureConnector

    # get_or_create_connector reads _CONNECTOR_CLASSES directly, so
    # register the class there (monkeypatch undoes it after the test).
    monkeypatch.setitem(
        registry_mod._CONNECTOR_CLASSES, CONNECTOR_ID, SafetyCultureConnector
    )
    tenant = "tenant-rotate-secret"
    try:
        first = client.post(
            f"/api/v1/integrations/configure/{tenant}",
            json={"connector_id": CONNECTOR_ID, "api_key": "k", "webhook_secret": "secret-one"},
        )
        assert first.status_code == 200
        assert registry_mod.get_tenant_connectors(tenant)[CONNECTOR_ID].config.webhook_secret == "secret-one"

        second = client.post(
            f"/api/v1/integrations/configure/{tenant}",
            json={"connector_id": CONNECTOR_ID, "api_key": "k", "webhook_secret": "secret-two"},
        )
        assert second.status_code == 200
        connector = registry_mod.get_tenant_connectors(tenant)[CONNECTOR_ID]
        assert connector.config.webhook_secret == "secret-two"
    finally:
        registry_mod.remove_connector(tenant, CONNECTOR_ID)
