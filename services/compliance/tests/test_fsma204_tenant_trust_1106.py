"""Regression tests for #1106 — FDA spreadsheet route tenant trust.

Before this fix the ``/v1/fsma/audit/spreadsheet`` handler read
``X-Tenant-ID`` / ``X-RegEngine-Tenant-ID`` from the client and
forwarded it to graph-service without verifying it matched the
authenticated API key's ``tenant_id``. A legitimately authenticated
caller for tenant A could therefore set ``X-Tenant-ID: tenantB`` and
obtain another tenant's FDA package.

These tests lock in two guarantees:

1. The in-process event query always uses the authenticated tenant id
   (never the client-supplied header).
2. A client-supplied tenant header that disagrees with the API
   key's tenant is rejected with HTTP 409 ``E_TENANT_MISMATCH``.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

service_dir = Path(__file__).parent.parent
for key in list(sys.modules):
    if key == "app" or key.startswith("services.compliance.app.") or key == "main":
        del sys.modules[key]
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

TENANT_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TENANT_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _fresh_routes():
    if "services.compliance.app.routes" in sys.modules:
        return sys.modules["services.compliance.app.routes"]
    return importlib.import_module("services.compliance.app.routes")


class _StubPrincipal:
    """Stands in for a validated APIKey. The route reads ``tenant_id``
    and ``key_id`` off it; nothing else is needed.
    """

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.key_id = "test-key"


def _recording_loader(captured: dict, events: list[dict]):
    """Record kwargs passed to the in-process event loader."""

    def _load(**kwargs):
        captured.update(kwargs)
        return events

    return _load


def _make_client(tenant_id: str):
    """Build a TestClient whose ``require_api_key`` dep returns a
    principal bound to ``tenant_id``.
    """
    from shared.auth import require_api_key

    routes_mod = _fresh_routes()
    app = FastAPI()
    app.include_router(routes_mod.router)
    app.dependency_overrides[require_api_key] = lambda: _StubPrincipal(tenant_id)

    c = TestClient(app)
    c._routes_mod = routes_mod  # type: ignore[attr-defined]
    return c


def _minimal_event() -> dict:
    return {
        "type": "SHIPPING",
        "tlc": "TLC-001",
        "product_description": "Romaine",
        "quantity": 100,
        "uom": "cases",
        "kdes": {"event_date": "2026-04-10T10:00:00+00:00"},
    }


# ---------------------------------------------------------------------------
# #1106 — client-supplied X-Tenant-ID is ignored; authenticated tenant wins
# ---------------------------------------------------------------------------


def test_fsma204_ignores_client_tenant_header():
    """Authenticate as tenant A, pass no conflicting header — the
    in-process query is scoped to tenant A's id.
    """
    client = _make_client(TENANT_A)
    captured: dict = {}
    with patch.object(
        client._routes_mod,
        "_load_fsma_audit_events",
        side_effect=_recording_loader(captured, [_minimal_event()]),
    ):
        r = client.get(
            "/v1/fsma/audit/spreadsheet",
            params={"start_date": "2026-04-01", "end_date": "2026-04-17"},
            headers={"X-RegEngine-API-Key": "rge_caller_raw_key_should_not_leak"},
        )

    assert r.status_code == 200, r.text
    assert captured["tenant_id"] == TENANT_A


def test_fsma204_ignores_client_tenant_header_matching_values():
    """When the client sends a matching header, it's still the
    API-key-derived value that scopes the query.
    """
    client = _make_client(TENANT_A)
    captured: dict = {}
    with patch.object(
        client._routes_mod,
        "_load_fsma_audit_events",
        side_effect=_recording_loader(captured, [_minimal_event()]),
    ):
        r = client.get(
            "/v1/fsma/audit/spreadsheet",
            params={"start_date": "2026-04-01", "end_date": "2026-04-17"},
            headers={"X-Tenant-ID": TENANT_A},
        )

    assert r.status_code == 200, r.text
    assert captured["tenant_id"] == TENANT_A


# ---------------------------------------------------------------------------
# #1106 — mismatched tenant header → 409 E_TENANT_MISMATCH
# ---------------------------------------------------------------------------


def test_fsma204_rejects_mismatched_x_tenant_id_header():
    """Authenticate as tenant A, pass ``X-Tenant-ID: tenantB`` →
    HTTP 409 with ``E_TENANT_MISMATCH`` and no downstream call
    (the request is rejected before the graph fetch runs).
    """
    client = _make_client(TENANT_A)
    captured: dict = {}
    with patch.object(
        client._routes_mod,
        "_load_fsma_audit_events",
        side_effect=_recording_loader(captured, [_minimal_event()]),
    ):
        r = client.get(
            "/v1/fsma/audit/spreadsheet",
            params={"start_date": "2026-04-01", "end_date": "2026-04-17"},
            headers={"X-Tenant-ID": TENANT_B},
        )

    assert r.status_code == 409, r.text
    assert r.json()["detail"] == "E_TENANT_MISMATCH"
    # Request must have been rejected BEFORE the downstream call.
    assert captured == {}


def test_fsma204_rejects_mismatched_x_regengine_tenant_id_header():
    """Same rejection applies for the legacy
    ``X-RegEngine-Tenant-ID`` alias.
    """
    client = _make_client(TENANT_A)
    captured: dict = {}
    with patch.object(
        client._routes_mod,
        "_load_fsma_audit_events",
        side_effect=_recording_loader(captured, [_minimal_event()]),
    ):
        r = client.get(
            "/v1/fsma/audit/spreadsheet",
            params={"start_date": "2026-04-01", "end_date": "2026-04-17"},
            headers={"X-RegEngine-Tenant-ID": TENANT_B},
        )

    assert r.status_code == 409, r.text
    assert r.json()["detail"] == "E_TENANT_MISMATCH"
    assert captured == {}


# ---------------------------------------------------------------------------
# #1106 — API key without tenant must be rejected
# ---------------------------------------------------------------------------


def test_fsma204_rejects_api_key_without_tenant():
    """A principal with no ``tenant_id`` must be rejected
    (403), never silently used with a client-supplied header.
    """
    from shared.auth import require_api_key

    routes_mod = _fresh_routes()
    app = FastAPI()
    app.include_router(routes_mod.router)
    app.dependency_overrides[require_api_key] = lambda: _StubPrincipal(tenant_id=None)

    c = TestClient(app)
    r = c.get(
        "/v1/fsma/audit/spreadsheet",
        params={"start_date": "2026-04-01", "end_date": "2026-04-17"},
        headers={"X-Tenant-ID": TENANT_B},
    )
    assert r.status_code == 403, r.text
    assert "tenant" in r.json()["detail"].lower()
