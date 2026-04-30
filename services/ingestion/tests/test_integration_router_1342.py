"""Dedicated tests for the integrations API router — #1342.

Context
-------
``services/ingestion/app/integration_router.py`` exposes 7 endpoints
that configure, test, and operate external-system connectors:

* ``GET  /api/v1/integrations/available``
* ``GET  /api/v1/integrations/status/{tenant_id}``
* ``POST /api/v1/integrations/configure/{tenant_id}``
* ``POST /api/v1/integrations/test/{tenant_id}/{connector_id}``
* ``POST /api/v1/integrations/sync/{tenant_id}``
* ``POST /api/v1/integrations/csv-upload/{tenant_id}``
* ``POST /api/v1/integrations/webhook/{tenant_id}/{connector_id}``
* ``DELETE /api/v1/integrations/disconnect/{tenant_id}/{connector_id}``

Before this file there was no direct test coverage — a regression in
the 404/501/401 branches of the webhook handler, or in the tenant-
scoped connector lookup, could ship invisibly.

The suite uses monkeypatching of ``shared.external_connectors.registry``
functions (imported lazily inside each handler) to exercise the
router without standing up real connectors or SFTP endpoints.
"""

from __future__ import annotations

import io
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# Make services/ingestion importable.
service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app import integration_router  # noqa: E402
from app.webhook_compat import _verify_api_key  # noqa: E402
from shared.external_connectors import registry as registry_mod  # noqa: E402
from shared.external_connectors.base import ConnectionStatus, ConnectorConfig  # noqa: E402


TENANT = "tenant-integ-1"
CONNECTOR_ID = "safetyculture"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _FakeConnector:
    """Stand-in for a concrete IntegrationConnector subclass."""

    def __init__(
        self,
        status: ConnectionStatus = ConnectionStatus.CONNECTED,
        test_result: bool = True,
    ):
        self.status = status
        self._test_result = test_result
        self.sync_called_with: Dict[str, Any] = {}
        self.webhook_called_with: Dict[str, Any] = {}

    async def test_connection(self):
        return self._test_result

    async def sync(self, *, since=None, limit=100):
        self.sync_called_with = {"since": since, "limit": limit}

        class _SyncResult:
            connector_id = CONNECTOR_ID
            events_fetched = 10
            events_accepted = 9
            events_rejected = 1
            errors: List[str] = []
            duration_ms = 123
            success = True

        return _SyncResult()

    async def handle_webhook(self, payload: bytes, headers: Dict[str, str]):
        self.webhook_called_with = {"payload": payload, "headers": headers}

        class _Event:
            def to_ingest_dict(self):
                return {"cte_type": "receiving", "tenant_id": TENANT}

        return [_Event(), _Event()]


@pytest.fixture
def app_with_auth_bypass():
    """Build a FastAPI app wearing the router with _verify_api_key
    stubbed to a no-op (tests exercising auth handle that separately)."""
    app = FastAPI()
    app.include_router(integration_router.router)

    # Dependency-override bypasses the auth gate so other contracts
    # are the subject of each test. The replacement MUST be a
    # zero-arg callable — if it takes ``*args/**kwargs`` FastAPI
    # tries to inject those as required query params.
    async def _noop():
        return None

    app.dependency_overrides[_verify_api_key] = _noop
    return app


@pytest.fixture
def client(app_with_auth_bypass):
    return TestClient(app_with_auth_bypass)


@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch):
    """Start every test from a clean connector registry so previous
    tests don't leak connector instances."""
    monkeypatch.setattr(registry_mod, "_CONNECTOR_CLASSES", {})
    monkeypatch.setattr(registry_mod, "_CONNECTOR_ALIASES", {})
    monkeypatch.setattr(registry_mod, "_ACTIVE_CONNECTORS", {})


# ---------------------------------------------------------------------------
# GET /available
# ---------------------------------------------------------------------------


class TestListAvailable:
    def test_returns_integrations_from_registry(self, client, monkeypatch):
        sample = [
            {"id": "safetyculture", "name": "SafetyCulture", "category": "food_safety"},
            {"id": "sap_s4hana", "name": "SAP S/4HANA", "category": "erp"},
        ]
        monkeypatch.setattr(
            registry_mod, "list_available_connectors", lambda: sample
        )
        resp = client.get("/api/v1/integrations/available")
        assert resp.status_code == 200
        assert resp.json() == {"integrations": sample}

    def test_empty_registry_returns_empty_list(self, client, monkeypatch):
        monkeypatch.setattr(registry_mod, "list_available_connectors", lambda: [])
        resp = client.get("/api/v1/integrations/available")
        assert resp.status_code == 200
        assert resp.json() == {"integrations": []}


# ---------------------------------------------------------------------------
# GET /status/{tenant_id}
# ---------------------------------------------------------------------------


class TestGetStatuses:
    def test_returns_statuses_for_tenant(self, client, monkeypatch):
        captured_tenant: Dict[str, str] = {}

        def _fake(tenant_id: str):
            captured_tenant["tid"] = tenant_id
            return [
                {"connector_id": "safetyculture", "status": "connected"},
                {"connector_id": "sap_s4hana", "status": "disconnected"},
            ]

        monkeypatch.setattr(registry_mod, "get_all_integration_statuses", _fake)

        resp = client.get(f"/api/v1/integrations/status/{TENANT}")
        assert resp.status_code == 200
        # Handler passes the path param tenant_id through verbatim.
        assert captured_tenant["tid"] == TENANT
        assert len(resp.json()["integrations"]) == 2


# ---------------------------------------------------------------------------
# POST /configure/{tenant_id}
# ---------------------------------------------------------------------------


class TestConfigureConnector:
    def test_unknown_connector_returns_404(self, client, monkeypatch):
        """If the requested connector_id isn't registered, 404 with a
        diagnostic naming the bad ID — not a 500 from the None class."""
        monkeypatch.setattr(
            registry_mod, "get_connector_class", lambda _id: None
        )
        resp = client.post(
            f"/api/v1/integrations/configure/{TENANT}",
            json={"connector_id": "nonexistent"},
        )
        assert resp.status_code == 404
        assert "nonexistent" in resp.json()["detail"]

    def test_happy_path_creates_connector(self, client, monkeypatch):
        """Valid connector_id + credentials → persisted + status echoed."""

        class _FakeClass:
            def __init__(self, config):
                self._config = config

            def get_connector_info(self):
                return {"id": CONNECTOR_ID, "category": "food_safety"}

        created = {}

        def _get_or_create(tenant_id, connector_id, config):
            created["tenant_id"] = tenant_id
            created["connector_id"] = connector_id
            created["config"] = config
            return _FakeConnector(status=ConnectionStatus.CONNECTED)

        monkeypatch.setattr(registry_mod, "get_connector_class", lambda _id: _FakeClass)
        monkeypatch.setattr(registry_mod, "get_or_create_connector", _get_or_create)

        resp = client.post(
            f"/api/v1/integrations/configure/{TENANT}",
            json={
                "connector_id": CONNECTOR_ID,
                "api_key": "sk_test_123",
                "base_url": "https://api.example.com",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body == {
            "configured": True,
            "connector_id": CONNECTOR_ID,
            "status": "connected",
        }
        assert created["tenant_id"] == TENANT
        assert created["config"].api_key == "sk_test_123"
        assert created["config"].base_url == "https://api.example.com"

    def test_public_slug_alias_configures_canonical_connector(
        self, client, monkeypatch
    ):
        """Public docs/UI slugs should work even when the backend stores
        an older underscore connector ID."""

        class _FakeClass:
            def __init__(self, config):
                self._config = config

            def get_connector_info(self):
                return {"id": "inflow_lab", "category": "developer"}

        created = {}

        def _get_or_create(tenant_id, connector_id, config):
            created["tenant_id"] = tenant_id
            created["connector_id"] = connector_id
            created["config"] = config
            return _FakeConnector(status=ConnectionStatus.CONNECTED)

        monkeypatch.setattr(
            registry_mod, "_CONNECTOR_CLASSES", {"inflow_lab": _FakeClass}
        )
        monkeypatch.setattr(
            registry_mod, "_CONNECTOR_ALIASES", {"inflow-lab": "inflow_lab"}
        )
        monkeypatch.setattr(registry_mod, "get_or_create_connector", _get_or_create)

        resp = client.post(
            f"/api/v1/integrations/configure/{TENANT}",
            json={"connector_id": "inflow-lab"},
        )

        assert resp.status_code == 200
        assert resp.json()["connector_id"] == "inflow_lab"
        assert created["connector_id"] == "inflow_lab"
        assert created["config"].connector_id == "inflow_lab"

    def test_category_falls_back_to_class_name_on_introspection_failure(
        self, client, monkeypatch
    ):
        """When the connector instantiation for info-lookup blows up, the
        handler falls back to class-name-based category rather than
        returning 500. Important regression lock — a buggy third-party
        connector shouldn't brick the configure endpoint."""

        class _BoomClass:
            __name__ = "BoomClass"

            def __init__(self, config):
                raise RuntimeError("connector info boom")

        # Still allow creation to succeed later — the handler will
        # call _BoomClass(...) itself inside get_or_create? No —
        # get_or_create is monkeypatched separately.
        def _get_or_create(_tid, _cid, _cfg):
            return _FakeConnector()

        monkeypatch.setattr(registry_mod, "get_connector_class", lambda _id: _BoomClass)
        monkeypatch.setattr(registry_mod, "get_or_create_connector", _get_or_create)

        resp = client.post(
            f"/api/v1/integrations/configure/{TENANT}",
            json={"connector_id": "boom"},
        )
        # Handler must succeed — the category fallback path is
        # exercised, not the failure path.
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /test/{tenant_id}/{connector_id}
# ---------------------------------------------------------------------------


class TestConnection:
    def test_unconfigured_connector_returns_404(self, client, monkeypatch):
        monkeypatch.setattr(
            registry_mod, "get_tenant_connectors", lambda _tid: {}
        )
        resp = client.post(
            f"/api/v1/integrations/test/{TENANT}/{CONNECTOR_ID}"
        )
        assert resp.status_code == 404
        assert CONNECTOR_ID in resp.json()["detail"]
        assert TENANT in resp.json()["detail"]

    def test_configured_connector_returns_connection_state(
        self, client, monkeypatch
    ):
        connector = _FakeConnector(
            status=ConnectionStatus.CONNECTED, test_result=True
        )
        monkeypatch.setattr(
            registry_mod,
            "get_tenant_connectors",
            lambda _tid: {CONNECTOR_ID: connector},
        )
        resp = client.post(
            f"/api/v1/integrations/test/{TENANT}/{CONNECTOR_ID}"
        )
        assert resp.status_code == 200
        assert resp.json() == {
            "connector_id": CONNECTOR_ID,
            "connected": True,
            "status": "connected",
        }

    def test_public_slug_alias_reaches_configured_connector(
        self, client, monkeypatch
    ):
        connector = _FakeConnector(
            status=ConnectionStatus.CONNECTED, test_result=True
        )
        monkeypatch.setattr(
            registry_mod, "_CONNECTOR_ALIASES", {"inflow-lab": "inflow_lab"}
        )
        monkeypatch.setattr(
            registry_mod,
            "get_tenant_connectors",
            lambda _tid: {"inflow_lab": connector},
        )

        resp = client.post(f"/api/v1/integrations/test/{TENANT}/inflow-lab")

        assert resp.status_code == 200
        assert resp.json()["connector_id"] == "inflow_lab"

    def test_connection_test_failure_still_returns_200(self, client, monkeypatch):
        """A failed ``test_connection`` is not an API-error condition —
        it's useful DIAGNOSTIC output. The endpoint should return 200
        with ``connected=False`` so the UI can show a health badge."""
        connector = _FakeConnector(
            status=ConnectionStatus.ERROR, test_result=False
        )
        monkeypatch.setattr(
            registry_mod,
            "get_tenant_connectors",
            lambda _tid: {CONNECTOR_ID: connector},
        )
        resp = client.post(
            f"/api/v1/integrations/test/{TENANT}/{CONNECTOR_ID}"
        )
        assert resp.status_code == 200
        assert resp.json()["connected"] is False
        assert resp.json()["status"] == "error"


# ---------------------------------------------------------------------------
# POST /sync/{tenant_id}
# ---------------------------------------------------------------------------


class TestTriggerSync:
    def test_unconfigured_connector_returns_404(self, client, monkeypatch):
        monkeypatch.setattr(
            registry_mod, "get_tenant_connectors", lambda _tid: {}
        )
        resp = client.post(
            f"/api/v1/integrations/sync/{TENANT}",
            json={"connector_id": CONNECTOR_ID},
        )
        assert resp.status_code == 404

    def test_happy_path_returns_sync_result(self, client, monkeypatch):
        connector = _FakeConnector()
        monkeypatch.setattr(
            registry_mod,
            "get_tenant_connectors",
            lambda _tid: {CONNECTOR_ID: connector},
        )
        resp = client.post(
            f"/api/v1/integrations/sync/{TENANT}",
            json={"connector_id": CONNECTOR_ID, "limit": 50},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["connector_id"] == CONNECTOR_ID
        assert body["events_fetched"] == 10
        assert body["events_accepted"] == 9
        assert body["events_rejected"] == 1
        assert body["success"] is True
        assert connector.sync_called_with["limit"] == 50

    def test_since_iso_parsed_with_z_suffix(self, client, monkeypatch):
        """``since`` is documented as ISO 8601 — the handler normalizes
        the Zulu ``Z`` suffix to ``+00:00`` before fromisoformat.
        Lock this so Python 3.10 compatibility doesn't silently
        regress."""
        connector = _FakeConnector()
        monkeypatch.setattr(
            registry_mod,
            "get_tenant_connectors",
            lambda _tid: {CONNECTOR_ID: connector},
        )
        resp = client.post(
            f"/api/v1/integrations/sync/{TENANT}",
            json={
                "connector_id": CONNECTOR_ID,
                "since": "2026-04-18T00:00:00Z",
            },
        )
        assert resp.status_code == 200
        since = connector.sync_called_with["since"]
        assert isinstance(since, datetime)
        assert since.tzinfo is not None
        assert since.utcoffset().total_seconds() == 0

    def test_since_none_passes_none(self, client, monkeypatch):
        connector = _FakeConnector()
        monkeypatch.setattr(
            registry_mod,
            "get_tenant_connectors",
            lambda _tid: {CONNECTOR_ID: connector},
        )
        client.post(
            f"/api/v1/integrations/sync/{TENANT}",
            json={"connector_id": CONNECTOR_ID},
        )
        assert connector.sync_called_with["since"] is None


# ---------------------------------------------------------------------------
# POST /csv-upload/{tenant_id}
# ---------------------------------------------------------------------------


class TestCsvUpload:
    def test_csv_upload_parses_rows(self, client, monkeypatch):
        """CSV is passed to CSVSFTPConnector.parse_csv — mock the
        connector so we can assert the handler wires source_system,
        default_cte_type, and the BOM-handling decode correctly."""

        class _FakeEvent:
            def to_ingest_dict(self):
                return {"event_type": "receiving"}

        parsed_with = {}

        class _FakeCSVConnector:
            def __init__(self, config):
                self.config = config

            def parse_csv(self, csv_text, source_file):
                parsed_with["csv_text"] = csv_text
                parsed_with["source_file"] = source_file
                parsed_with["tenant_id"] = self.config.tenant_id
                return [_FakeEvent(), _FakeEvent(), _FakeEvent()]

        from shared.external_connectors import csv_sftp

        monkeypatch.setattr(csv_sftp, "CSVSFTPConnector", _FakeCSVConnector)

        csv_content = "lot_id,qty\nLOT-1,10\n".encode("utf-8-sig")
        resp = client.post(
            f"/api/v1/integrations/csv-upload/{TENANT}",
            params={"source_system": "sap", "default_cte_type": "harvesting"},
            files={"file": ("receiving.csv", csv_content, "text/csv")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["filename"] == "receiving.csv"
        assert body["rows_parsed"] == 3
        assert body["source_system"] == "sap"
        assert body["default_cte_type"] == "harvesting"
        assert parsed_with["tenant_id"] == TENANT
        assert parsed_with["source_file"] == "receiving.csv"
        assert "LOT-1" in parsed_with["csv_text"]

    def test_csv_upload_handles_bom(self, client, monkeypatch):
        """Files exported from Excel start with ``\\ufeff``. The
        handler decodes as ``utf-8-sig`` to strip it. Without this
        guard the first column header would carry the BOM and break
        column mapping silently."""

        class _FakeCSVConnector:
            def __init__(self, config):
                pass

            def parse_csv(self, csv_text, source_file):
                # The BOM must NOT be present in the decoded text.
                assert not csv_text.startswith("\ufeff")
                return []

        from shared.external_connectors import csv_sftp

        monkeypatch.setattr(csv_sftp, "CSVSFTPConnector", _FakeCSVConnector)

        # Actually include a BOM at the top of the bytes.
        csv_bytes = ("\ufefflot_id,qty\nLOT-1,10\n").encode("utf-8")
        resp = client.post(
            f"/api/v1/integrations/csv-upload/{TENANT}",
            files={"file": ("bom.csv", csv_bytes, "text/csv")},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /webhook/{tenant_id}/{connector_id}
# ---------------------------------------------------------------------------


class TestInboundWebhook:
    """Webhook endpoint is intentionally unauthenticated at the router
    layer — it validates signatures via ``connector.handle_webhook``."""

    def test_unconfigured_connector_returns_404(self, client, monkeypatch):
        monkeypatch.setattr(
            registry_mod, "get_tenant_connectors", lambda _tid: {}
        )
        resp = client.post(
            f"/api/v1/integrations/webhook/{TENANT}/{CONNECTOR_ID}",
            json={"event": "ping"},
        )
        assert resp.status_code == 404

    def test_happy_path_returns_accepted_events(self, client, monkeypatch):
        connector = _FakeConnector()
        monkeypatch.setattr(
            registry_mod,
            "get_tenant_connectors",
            lambda _tid: {CONNECTOR_ID: connector},
        )
        resp = client.post(
            f"/api/v1/integrations/webhook/{TENANT}/{CONNECTOR_ID}",
            json={"event": "audit_completed"},
            headers={"X-Signature": "sha256=abc123"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["accepted"] == 2
        assert len(body["events"]) == 2
        # Signature header was passed through for the connector to
        # verify — not stripped by the router.
        assert connector.webhook_called_with["headers"].get("x-signature") == "sha256=abc123"

    def test_unsupported_webhook_returns_501(self, client, monkeypatch):
        """Some connectors are pull-only. ``NotImplementedError`` from
        ``handle_webhook`` must surface as 501 Not Implemented — not
        500, so clients get a clear signal to disable the webhook."""

        class _NoWebhookConnector(_FakeConnector):
            async def handle_webhook(self, payload, headers):  # type: ignore[override]
                raise NotImplementedError("pull-only")

        monkeypatch.setattr(
            registry_mod,
            "get_tenant_connectors",
            lambda _tid: {CONNECTOR_ID: _NoWebhookConnector()},
        )
        resp = client.post(
            f"/api/v1/integrations/webhook/{TENANT}/{CONNECTOR_ID}",
            json={"event": "ping"},
        )
        assert resp.status_code == 501
        assert "does not support webhooks" in resp.json()["detail"]

    def test_signature_failure_returns_401(self, client, monkeypatch):
        """Bad signature should surface as 401, not a 500 from an
        unhandled ValueError. Key defense: don't leak trace info to
        unauthenticated callers."""

        class _BadSigConnector(_FakeConnector):
            async def handle_webhook(self, payload, headers):  # type: ignore[override]
                raise ValueError("invalid signature")

        monkeypatch.setattr(
            registry_mod,
            "get_tenant_connectors",
            lambda _tid: {CONNECTOR_ID: _BadSigConnector()},
        )
        resp = client.post(
            f"/api/v1/integrations/webhook/{TENANT}/{CONNECTOR_ID}",
            json={"event": "ping"},
        )
        assert resp.status_code == 401
        assert "invalid signature" in resp.json()["detail"]

    def test_webhook_payload_passed_as_raw_bytes(self, client, monkeypatch):
        """The connector receives the raw request body (not JSON-decoded)
        so it can compute signatures over the original bytes."""
        connector = _FakeConnector()
        monkeypatch.setattr(
            registry_mod,
            "get_tenant_connectors",
            lambda _tid: {CONNECTOR_ID: connector},
        )
        client.post(
            f"/api/v1/integrations/webhook/{TENANT}/{CONNECTOR_ID}",
            content=b'{"raw":true}',
            headers={"Content-Type": "application/json"},
        )
        assert connector.webhook_called_with["payload"] == b'{"raw":true}'


# ---------------------------------------------------------------------------
# DELETE /disconnect/{tenant_id}/{connector_id}
# ---------------------------------------------------------------------------


class TestDisconnect:
    def test_disconnect_calls_registry_and_returns_flag(
        self, client, monkeypatch
    ):
        removed: Dict[str, str] = {}

        def _remove(tenant_id, connector_id):
            removed["tenant_id"] = tenant_id
            removed["connector_id"] = connector_id

        monkeypatch.setattr(registry_mod, "remove_connector", _remove)
        resp = client.delete(
            f"/api/v1/integrations/disconnect/{TENANT}/{CONNECTOR_ID}"
        )
        assert resp.status_code == 200
        assert resp.json() == {
            "disconnected": True,
            "connector_id": CONNECTOR_ID,
        }
        assert removed == {"tenant_id": TENANT, "connector_id": CONNECTOR_ID}

    def test_disconnect_idempotent_for_unknown_connector(
        self, client, monkeypatch
    ):
        """``remove_connector`` is a no-op if the connector isn't
        registered, so disconnect should return 200 rather than 404 —
        mirrors the ``pop(key, None)`` semantics of the registry."""
        monkeypatch.setattr(registry_mod, "remove_connector", lambda _t, _c: None)
        resp = client.delete(
            f"/api/v1/integrations/disconnect/{TENANT}/never-configured"
        )
        assert resp.status_code == 200
        assert resp.json()["disconnected"] is True


# ---------------------------------------------------------------------------
# Auth gate: ensure protected endpoints *would* 401 without bypass
# ---------------------------------------------------------------------------


class TestAuthGate:
    """Sanity check that the ``_verify_api_key`` dependency is actually
    wired to all non-webhook routes. Uses a FastAPI app WITHOUT the
    bypass override so the real dep fires."""

    @pytest.fixture
    def app_with_real_auth(self):
        app = FastAPI()
        app.include_router(integration_router.router)
        return app

    @pytest.fixture
    def unauth_client(self, app_with_real_auth):
        return TestClient(app_with_real_auth)

    @pytest.mark.parametrize(
        "method,path",
        [
            ("GET", "/api/v1/integrations/available"),
            ("GET", f"/api/v1/integrations/status/{TENANT}"),
            ("POST", f"/api/v1/integrations/configure/{TENANT}"),
            ("POST", f"/api/v1/integrations/test/{TENANT}/{CONNECTOR_ID}"),
            ("POST", f"/api/v1/integrations/sync/{TENANT}"),
            ("DELETE", f"/api/v1/integrations/disconnect/{TENANT}/{CONNECTOR_ID}"),
        ],
    )
    def test_protected_endpoint_requires_api_key(
        self, unauth_client, method, path
    ):
        """Without an API key header these endpoints should NOT be
        open — anything other than 200 is acceptable (exact status
        code depends on how ``_verify_api_key`` formats the error)."""
        if method == "GET":
            resp = unauth_client.get(path)
        elif method == "DELETE":
            resp = unauth_client.delete(path)
        else:
            resp = unauth_client.post(path, json={"connector_id": CONNECTOR_ID})
        # The key assertion is "NOT 200" — we don't want an
        # un-authed 200 from any of these routes.
        assert resp.status_code != 200, (
            f"{method} {path} returned 200 without API-key; "
            "auth dependency isn't wired"
        )

    def test_webhook_endpoint_does_NOT_require_api_key(
        self, unauth_client, monkeypatch
    ):
        """The webhook endpoint is intentionally open — it authenticates
        via the connector's webhook signature, not a platform API key.
        Regressing this to require auth would break every partner
        integration silently."""
        monkeypatch.setattr(
            registry_mod, "get_tenant_connectors", lambda _tid: {}
        )
        # 404 is OK (no connector) — what we're asserting is that we
        # reached the handler without a pre-handler 401.
        resp = unauth_client.post(
            f"/api/v1/integrations/webhook/{TENANT}/{CONNECTOR_ID}",
            json={"event": "ping"},
        )
        assert resp.status_code != 401, (
            "Webhook endpoint should not require platform API key auth"
        )
