"""Data-free XML route checks.

Strict-mode per-index 422 and ``E_EPCIS_UNVALIDATED`` need a structurally
valid EPCIS document. No real document is available.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    from app.epcis.router import router
    from app.webhook_compat import _verify_api_key

    from services.ingestion.tests.tenant_context_overrides import install_tenant_context_override

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    install_tenant_context_override(app, default_tenant="00000000-0000-0000-0000-000000000123")
    return TestClient(app, raise_server_exceptions=False)


def test_empty_xml_body_returns_400_without_traceback(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/epcis/events/xml",
        content=b"",
        headers={"Content-Type": "application/xml"},
    )
    assert resp.status_code == 400
    assert "Empty XML payload" in resp.json()["detail"]
    assert "Traceback" not in resp.text


def test_non_xml_body_returns_400_without_traceback(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/epcis/events/xml",
        content=b"not xml at all",
        headers={"Content-Type": "application/xml"},
    )
    assert resp.status_code == 400
    assert "does not appear to be XML" in resp.json()["detail"]
    assert "Traceback" not in resp.text


def test_parser_returning_no_events_returns_422(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.epcis import router as router_mod

    monkeypatch.setattr(router_mod, "_parse_epcis_xml", lambda raw: [])
    resp = client.post(
        "/api/v1/epcis/events/xml",
        content=b"<root/>",
        headers={"Content-Type": "application/xml"},
    )
    assert resp.status_code == 422
    assert "No EPCIS events found" in resp.json()["detail"]
    assert "Traceback" not in resp.text
