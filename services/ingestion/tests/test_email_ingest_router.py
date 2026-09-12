"""Unit tests for ``app.email_ingest.router`` — the Postmark webhook endpoint.

Uses a standalone ``FastAPI`` app carrying only this router (same pattern as
``services/ingestion/tests/remediation/conftest.py``'s ``client`` fixture),
with ``process_inbound_email`` monkeypatched so no DB or CSV pipeline runs —
these tests are about auth wiring, status codes, and request/response shape,
not the orchestration logic itself (covered by ``test_email_ingest_service.py``).
"""

from __future__ import annotations

import base64

import app.email_ingest.router as router_mod
import pytest
from app.email_ingest.router import router
from app.email_ingest.schemas import InboundEmailResult
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared.database import get_db_session

_USER = "postmark"
_PASSWORD = "s3cret"  # pragma: allowlist secret


def _auth_header(user: str = _USER, password: str = _PASSWORD) -> dict[str, str]:
    token = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
    return {"Authorization": f"Basic {token}"}


@pytest.fixture(autouse=True)
def _configure_auth(monkeypatch):
    monkeypatch.setenv("EMAIL_INBOUND_BASIC_AUTH_USER", _USER)
    monkeypatch.setenv("EMAIL_INBOUND_BASIC_AUTH_PASSWORD", _PASSWORD)


def _fake_session_dependency(session):
    """A generator-function dependency override, matching the shape FastAPI
    expects of ``get_db_session`` itself (a plain callable returning the
    value directly is NOT treated as yielding a dependency)."""

    def _dep():
        yield session

    return _dep


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db_session] = _fake_session_dependency(object())
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()


MINIMAL_PAYLOAD = {
    "MessageID": "msg-1",
    "From": "sender@example.com",
    "OriginalRecipient": "tenant@tenant.regengine.co",
}


class TestAuthGate:
    def test_missing_authorization_header_is_401(self, client):
        resp = client.post("/webhooks/email/inbound", json=MINIMAL_PAYLOAD)
        assert resp.status_code == 401

    def test_wrong_credentials_are_401(self, client):
        resp = client.post(
            "/webhooks/email/inbound",
            json=MINIMAL_PAYLOAD,
            headers=_auth_header(password="wrong"),
        )
        assert resp.status_code == 401

    def test_auth_not_configured_is_401(self, client, monkeypatch):
        monkeypatch.delenv("EMAIL_INBOUND_BASIC_AUTH_USER", raising=False)
        monkeypatch.delenv("EMAIL_INBOUND_BASIC_AUTH_PASSWORD", raising=False)
        resp = client.post(
            "/webhooks/email/inbound",
            json=MINIMAL_PAYLOAD,
            headers=_auth_header(),
        )
        assert resp.status_code == 401


class TestPayloadValidation:
    def test_missing_required_field_is_422(self, client):
        resp = client.post(
            "/webhooks/email/inbound",
            json={"From": "sender@example.com"},  # MessageID missing
            headers=_auth_header(),
        )
        assert resp.status_code == 422

    def test_unknown_postmark_fields_do_not_break_validation(self, client, monkeypatch):
        async def fake_process(db_session, payload):
            return InboundEmailResult(message_id=payload.MessageID, status="accepted", tenant_id="tenant-1")

        monkeypatch.setattr(router_mod, "process_inbound_email", fake_process)

        resp = client.post(
            "/webhooks/email/inbound",
            json={**MINIMAL_PAYLOAD, "SpamScore": "0.1", "HtmlBody": "<p>hi</p>"},
            headers=_auth_header(),
        )
        assert resp.status_code == 200


class TestDatabaseUnavailable:
    def test_none_session_returns_503(self, monkeypatch):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db_session] = _fake_session_dependency(None)
        with TestClient(app) as tc:
            resp = tc.post("/webhooks/email/inbound", json=MINIMAL_PAYLOAD, headers=_auth_header())
        assert resp.status_code == 503


class TestHappyPath:
    def test_delegates_to_process_inbound_email_and_returns_its_result(self, client, monkeypatch):
        captured = {}

        async def fake_process(db_session, payload):
            captured["payload"] = payload
            return InboundEmailResult(
                message_id=payload.MessageID,
                status="accepted",
                tenant_id="tenant-1",
                attachments=[],
            )

        monkeypatch.setattr(router_mod, "process_inbound_email", fake_process)

        resp = client.post("/webhooks/email/inbound", json=MINIMAL_PAYLOAD, headers=_auth_header())

        assert resp.status_code == 200
        body = resp.json()
        assert body["message_id"] == "msg-1"
        assert body["status"] == "accepted"
        assert body["tenant_id"] == "tenant-1"
        assert captured["payload"].MessageID == "msg-1"

    def test_rejection_is_still_a_200(self, client, monkeypatch):
        # Provider webhooks retry on 5xx — a data-quality rejection must
        # never look like a transient failure to Postmark.
        async def fake_process(db_session, payload):
            return InboundEmailResult(message_id=payload.MessageID, status="rejected", rejection_reason="unmapped_recipient")

        monkeypatch.setattr(router_mod, "process_inbound_email", fake_process)

        resp = client.post("/webhooks/email/inbound", json=MINIMAL_PAYLOAD, headers=_auth_header())
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"
