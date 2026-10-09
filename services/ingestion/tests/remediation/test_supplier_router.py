"""Focused unit tests for the supplier remediation router.

Uses fakes and mocks only: no database, no network, no real tokens.
Covers the token preview, exchange, session state, correction submit
(released and still-blocked paths), the static form page, and edge and
error cases (database unavailable, rate limiting, missing session).
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.remediation.supplier_router as sup_mod  # noqa: E402
from app.remediation.supplier_router import router as supplier_router  # noqa: E402
from shared.database import get_db_session  # noqa: E402

TOKEN = "T" * 32
SESSION = "S" * 32

CASE_ID = "11111111-1111-4111-8111-111111111111"
TENANT_ID = "22222222-2222-4222-8222-222222222222"


def _public_ctx(**overrides: Any) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {
        "case_id": CASE_ID,
        "status": "awaiting_supplier",
        "supplier": "Valley Farms LLC",
        "manifest": "MAN-1",
        "line": "line 2",
        "due_at": None,
        "authorized_fields": [{"field_path": "kdes.tlc_source_reference"}],
        "current_values": {"kdes.tlc_source_reference": None},
        "failures": [],
    }
    ctx.update(overrides)
    return ctx


def _full_ctx(**overrides: Any) -> Dict[str, Any]:
    case = {
        "id": CASE_ID,
        "status": "awaiting_supplier",
        "supplier_org": "Valley Farms LLC",
        "manifest_ref": "MAN-1",
        "line_ref": "line 2",
        "due_at": None,
        "allowed_fields": [{"field_path": "kdes.tlc_source_reference", "issue_id": "iss-1"}],
        "manifest_record_id": "rec-1",
    }
    record = {
        "id": "rec-1",
        "normalized_payload": {},
        "rule_failures": [],
        "field_provenance": {},
        "ingestion_run_id": "run-1",
    }
    ctx = _public_ctx()
    ctx["_case"] = case
    ctx["_record"] = record
    ctx.update(overrides)
    return ctx


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(sup_mod, "_consume_rate_limit", lambda **_kw: (True, 99))
    db = object()
    test_app = FastAPI()
    test_app.include_router(supplier_router)
    test_app.dependency_overrides[get_db_session] = lambda: db
    with TestClient(test_app) as tc:
        tc.db = db  # type: ignore[attr-defined]
        yield tc


def _valid_correction(**overrides: Any) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "changes": {"kdes.tlc_source_reference": "Valley Farms Packinghouse"},
        "actor_name": "Jordan Lee",
        "actor_role": "Logistics Coordinator",
        "reason": "TLC source omitted from export",
        "attestation": {
            "text": "I attest this correction is accurate.",
            "accepted": True,
        },
    }
    body.update(overrides)
    return body


def test_form_page_is_static_html(client):
    response = client.get("/api/v1/remediation/supplier/form")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "location.hash" in response.text


def test_context_preview_returns_public_fields_only(client, monkeypatch):
    monkeypatch.setattr(sup_mod.tokens, "resolve_active_token", lambda _db, _tok: {"tenant_id": TENANT_ID})
    monkeypatch.setattr(sup_mod, "_case_context", lambda _db, _row: _full_ctx())
    response = client.post("/api/v1/remediation/supplier/context", json={"token": TOKEN})
    assert response.status_code == 200
    body = response.json()
    assert body["case_id"] == CASE_ID
    assert body["status"] == "awaiting_supplier"
    assert "_case" not in body
    assert "_record" not in body


def test_context_db_unavailable_returns_503(monkeypatch):
    monkeypatch.setattr(sup_mod, "_consume_rate_limit", lambda **_kw: (True, 99))
    test_app = FastAPI()
    test_app.include_router(supplier_router)
    test_app.dependency_overrides[get_db_session] = lambda: None
    with TestClient(test_app) as no_db:
        response = no_db.post("/api/v1/remediation/supplier/context", json={"token": TOKEN})
    assert response.status_code == 503


def test_context_invalid_token_returns_uniform_400(client, monkeypatch):
    from fastapi import HTTPException

    def _boom(_db, _tok):
        raise HTTPException(status_code=400, detail="Remediation link is not usable")

    monkeypatch.setattr(sup_mod.tokens, "resolve_active_token", _boom)
    response = client.post("/api/v1/remediation/supplier/context", json={"token": TOKEN})
    assert response.status_code == 400
    assert response.json() == {"detail": "Remediation link is not usable"}


def test_exchange_returns_session_and_case(client, monkeypatch):
    token_row = {"tenant_id": TENANT_ID, "case_id": CASE_ID}
    monkeypatch.setattr(sup_mod.tokens, "resolve_active_token", lambda _db, _tok: token_row)
    monkeypatch.setattr(
        sup_mod.tokens,
        "exchange_for_session",
        lambda _db, _row: {
            "session_token": SESSION,
            "expires_at": datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        },
    )
    monkeypatch.setattr(sup_mod, "_case_context", lambda _db, _row: _full_ctx())
    response = client.post("/api/v1/remediation/supplier/exchange", json={"token": TOKEN})
    assert response.status_code == 200
    body = response.json()
    assert body["session_token"] == SESSION
    assert body["case"]["case_id"] == CASE_ID


def test_rate_limit_returns_429(client, monkeypatch):
    monkeypatch.setattr(sup_mod, "_consume_rate_limit", lambda **_kw: (False, 0))
    response = client.post("/api/v1/remediation/supplier/context", json={"token": TOKEN})
    assert response.status_code == 429


def test_session_current_requires_bearer_401(client):
    response = client.get("/api/v1/remediation/supplier/session/current")
    assert response.status_code == 401
    assert response.json() == {"detail": "Session is not valid"}


def test_session_current_returns_state(client, monkeypatch):
    monkeypatch.setattr(sup_mod.tokens, "resolve_active_session", lambda _db, _tok: {"tenant_id": TENANT_ID})
    monkeypatch.setattr(sup_mod, "_case_context", lambda _db, _row: _full_ctx())
    headers = {"Authorization": f"Bearer {SESSION}"}
    response = client.get("/api/v1/remediation/supplier/session/current", headers=headers)
    assert response.status_code == 200
    assert response.json()["case_id"] == CASE_ID


def _stub_submit_success(monkeypatch, *, blocking: bool):
    monkeypatch.setattr(sup_mod.tokens, "resolve_active_session", lambda *_a, **_k: {"tenant_id": TENANT_ID})
    monkeypatch.setattr(sup_mod, "_case_context", lambda _db, _row: _full_ctx())
    monkeypatch.setattr(sup_mod.corrections, "validate_field_path", lambda _p, _a: None)
    monkeypatch.setattr(sup_mod.corrections, "get_value", lambda _e, _p: None)
    monkeypatch.setattr(sup_mod.corrections, "set_value", lambda event, path, value: {**(event or {}), path: value})
    monkeypatch.setattr(sup_mod.corrections, "insert_patches", lambda *_a, **_kw: ["patch-1"])
    monkeypatch.setattr(sup_mod, "_store_provenance", lambda *_a, **_k: None)
    monkeypatch.setattr(sup_mod, "audit_event", lambda *_a, **_k: None)
    monkeypatch.setattr(sup_mod, "transition", lambda *_a, **_k: None)
    monkeypatch.setattr(sup_mod, "_resolve_exception", lambda *_a, **_k: None)
    monkeypatch.setattr(sup_mod, "_notify_buyer", lambda *_a, **_k: None)
    if blocking:
        monkeypatch.setattr(
            sup_mod.service,
            "revalidate_record",
            lambda *_a, **_kw: {"blocking": True, "failures": [{"why_failed": "still bad"}]},
        )
    else:
        monkeypatch.setattr(sup_mod.service, "revalidate_record", lambda *_a, **_kw: {"blocking": False})
        monkeypatch.setattr(sup_mod.service, "get_run_meta", lambda *_a, **_kw: {})
        monkeypatch.setattr(sup_mod.service, "release_record", lambda *_a, **_kw: "evt-1")


def test_submit_correction_released_path(client, monkeypatch):
    _stub_submit_success(monkeypatch, blocking=False)
    headers = {"Authorization": f"Bearer {SESSION}"}
    response = client.post(
        "/api/v1/remediation/supplier/session/corrections",
        headers=headers,
        json=_valid_correction(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "released"
    assert body["released_event_id"] == "evt-1"
    assert body["patch_ids"] == ["patch-1"]


def test_submit_correction_still_blocked_path(client, monkeypatch):
    _stub_submit_success(monkeypatch, blocking=True)
    headers = {"Authorization": f"Bearer {SESSION}"}
    response = client.post(
        "/api/v1/remediation/supplier/session/corrections",
        headers=headers,
        json=_valid_correction(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "still_blocked"
    assert body["failures"] == [{"why_failed": "still bad"}]


def test_submit_correction_attestation_required_422(client, monkeypatch):
    _stub_submit_success(monkeypatch, blocking=False)
    headers = {"Authorization": f"Bearer {SESSION}"}
    attestation = {"text": "I attest this correction is accurate.", "accepted": False}
    response = client.post(
        "/api/v1/remediation/supplier/session/corrections",
        headers=headers,
        json=_valid_correction(attestation=attestation),
    )
    assert response.status_code == 422


def test_submit_correction_wrong_status_409(client, monkeypatch):
    _stub_submit_success(monkeypatch, blocking=False)
    ctx = _full_ctx()
    ctx["_case"] = {**ctx["_case"], "status": "released"}
    monkeypatch.setattr(sup_mod, "_case_context", lambda _db, _row: ctx)
    headers = {"Authorization": f"Bearer {SESSION}"}
    response = client.post(
        "/api/v1/remediation/supplier/session/corrections",
        headers=headers,
        json=_valid_correction(),
    )
    assert response.status_code == 409


def test_submit_correction_value_too_long_422(client, monkeypatch):
    _stub_submit_success(monkeypatch, blocking=False)
    headers = {"Authorization": f"Bearer {SESSION}"}
    response = client.post(
        "/api/v1/remediation/supplier/session/corrections",
        headers=headers,
        json=_valid_correction(changes={"kdes.tlc_source_reference": "x" * 5000}),
    )
    assert response.status_code == 422


def test_case_context_builds_current_values(monkeypatch):
    import app.remediation.router as buyer_router

    case = {
        "id": CASE_ID,
        "status": "awaiting_supplier",
        "supplier_org": "Valley Farms LLC",
        "manifest_ref": "MAN-1",
        "line_ref": "line 2",
        "due_at": None,
        "allowed_fields": [{"field_path": "kdes.tlc_source_reference"}],
        "manifest_record_id": "rec-1",
    }
    record = {
        "normalized_payload": {"kdes": {"tlc_source_reference": "Packinghouse 7"}},
        "rule_failures": [{"why_failed": "x"}],
    }
    monkeypatch.setattr(buyer_router, "_load_case", lambda _db, _t, _c: case)
    monkeypatch.setattr(sup_mod.service, "load_record", lambda _db, **_kw: record)
    ctx = sup_mod._case_context(object(), {"tenant_id": TENANT_ID, "case_id": CASE_ID})
    assert ctx["current_values"] == {"kdes.tlc_source_reference": "Packinghouse 7"}
    assert ctx["failures"] == [{"why_failed": "x"}]
