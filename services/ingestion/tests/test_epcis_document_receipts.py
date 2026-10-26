"""EPCIS ingest routes write one document receipt per request body.

Persistence is stubbed and ``record_epcis_receipt`` is captured, so the tests
check what each route files (tenant, SHA-256 of the raw body, status, summary)
and that a failing receipt write leaves the ingest response unchanged. Ids and
payload values are generated per run.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

router_mod = importlib.import_module("app.epcis.router")
from app.webhook_compat import _verify_api_key  # noqa: E402
from shared.epcis_receipts import (  # noqa: E402
    MAX_ERROR_SUMMARY_LENGTH,
    RECEIPT_ACCEPTED,
    RECEIPT_REJECTED,
    document_sha256,
)
from shared.supplier_data_quality import MIN_RECORDS  # noqa: E402

from services.ingestion.tests.tenant_context_overrides import install_tenant_context_override  # noqa: E402

TENANT = str(uuid4())
# Batch size comes from the spec constant, not a picked number.
BATCH_SIZE = MIN_RECORDS


@pytest.fixture
def receipts(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    filed: list[dict] = []

    def _capture(tenant_id, raw_body, status, error_summary=None, session_factory=None):
        filed.append({"tenant_id": tenant_id, "raw_body": raw_body, "status": status, "error_summary": error_summary})
        return True

    monkeypatch.setattr(router_mod, "record_epcis_receipt", _capture)
    return filed


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router_mod.router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    install_tenant_context_override(app, default_tenant=TENANT, enforce_claims=True)
    with TestClient(app) as c:
        yield c


def _json_body(payload: dict) -> bytes:
    return json.dumps(payload).encode()


def _post_json(client: TestClient, path: str, payload: dict):
    raw = _json_body(payload)
    return raw, client.post(path, content=raw, headers={"Content-Type": "application/json"})


def _event() -> dict:
    return {"id": str(uuid4()), "value": str(uuid4())}


def _assert_receipt(receipt: dict, raw: bytes, status: str) -> None:
    assert receipt["tenant_id"] == TENANT
    assert receipt["raw_body"] == raw
    assert document_sha256(receipt["raw_body"]) == document_sha256(raw)
    assert receipt["status"] == status


# ── single event ─────────────────────────────────────────────────────────────


def test_accepted_event_files_accepted_receipt_with_raw_body(client, receipts, monkeypatch):
    created_id = str(uuid4())
    monkeypatch.setattr(router_mod, "_ingest_single_event", lambda t, e: ({"cte_id": created_id}, 201))
    raw, resp = _post_json(client, "/api/v1/epcis/events", _event())

    assert resp.status_code == 201
    assert resp.json() == {"cte_id": created_id}
    [receipt] = receipts
    _assert_receipt(receipt, raw, RECEIPT_ACCEPTED)
    assert receipt["error_summary"] is None


def test_validation_failure_files_rejected_receipt_without_payload(client, receipts, monkeypatch):
    event = _event()

    def _reject(_tenant, payload):
        # The message quotes the payload, as real validation messages can.
        raise HTTPException(
            status_code=422,
            detail={"error": "fsma_validation_failed", "message": f"bad value {payload['value']}"},
        )

    monkeypatch.setattr(router_mod, "_ingest_single_event", _reject)
    raw, resp = _post_json(client, "/api/v1/epcis/events", event)

    assert resp.status_code == 422
    [receipt] = receipts
    _assert_receipt(receipt, raw, RECEIPT_REJECTED)
    assert receipt["error_summary"] == "HTTPException 422 fsma_validation_failed"
    assert event["value"] not in receipt["error_summary"]


def test_unexpected_error_files_rejected_receipt_with_class_only(client, receipts, monkeypatch):
    event = _event()

    def _boom(_tenant, payload):
        raise RuntimeError(payload["value"])

    monkeypatch.setattr(router_mod, "_ingest_single_event", _boom)
    raw = _json_body(event)
    with pytest.raises(RuntimeError):
        client.post("/api/v1/epcis/events", content=raw, headers={"Content-Type": "application/json"})

    [receipt] = receipts
    _assert_receipt(receipt, raw, RECEIPT_REJECTED)
    assert receipt["error_summary"] == RuntimeError.__name__


def test_receipt_write_failure_does_not_change_the_response(client, monkeypatch):
    created_id = str(uuid4())
    monkeypatch.setattr(router_mod, "_ingest_single_event", lambda t, e: ({"cte_id": created_id}, 201))

    def _broken_session():
        raise ConnectionError(str(uuid4()))

    # The real writer runs; only the session factory fails.
    monkeypatch.setattr("shared.database.get_db_safe", _broken_session)
    _, resp = _post_json(client, "/api/v1/epcis/events", _event())

    assert resp.status_code == 201
    assert resp.json() == {"cte_id": created_id}


def test_receipt_write_failure_keeps_the_rejection(client, monkeypatch):
    def _reject(_tenant, _payload):
        raise HTTPException(status_code=422, detail={"error": "fsma_validation_failed"})

    monkeypatch.setattr(router_mod, "_ingest_single_event", _reject)
    monkeypatch.setattr("shared.database.get_db_safe", lambda: None)
    _, resp = _post_json(client, "/api/v1/epcis/events", _event())

    assert resp.status_code == 422
    assert resp.json()["detail"] == {"error": "fsma_validation_failed"}


# ── batch ────────────────────────────────────────────────────────────────────


def test_atomic_batch_files_one_accepted_receipt(client, receipts, monkeypatch):
    events = [_event() for _ in range(BATCH_SIZE)]
    monkeypatch.setattr(
        router_mod, "_ingest_batch_events_db_atomic", lambda t, evs: [({"cte_id": str(uuid4())}, 201) for _ in evs]
    )
    raw, resp = _post_json(client, "/api/v1/epcis/events/batch?mode=atomic", {"events": events})

    assert resp.status_code == 201
    [receipt] = receipts
    _assert_receipt(receipt, raw, RECEIPT_ACCEPTED)


def test_atomic_batch_validation_failure_files_rejected_receipt(client, receipts, monkeypatch):
    def _reject(_tenant, _events):
        raise HTTPException(status_code=400, detail={"error": "batch_validation_failed", "errors": _events})

    monkeypatch.setattr(router_mod, "_ingest_batch_events_db_atomic", _reject)
    events = [_event() for _ in range(BATCH_SIZE)]
    raw, resp = _post_json(client, "/api/v1/epcis/events/batch?mode=atomic", {"events": events})

    assert resp.status_code == 400
    [receipt] = receipts
    _assert_receipt(receipt, raw, RECEIPT_REJECTED)
    assert receipt["error_summary"] == "HTTPException 400 batch_validation_failed"
    assert all(event["value"] not in receipt["error_summary"] for event in events)


def test_partial_batch_with_some_failures_is_accepted_with_failed_count(client, receipts, monkeypatch):
    events = [_event() for _ in range(BATCH_SIZE)]
    failing = {event["id"] for event in events[::2]}

    def _single(_tenant, event):
        if event["id"] in failing:
            raise HTTPException(status_code=422, detail=event["value"])
        return {"cte_id": str(uuid4())}, 201

    monkeypatch.setattr(router_mod, "_ingest_single_event", _single)
    raw, resp = _post_json(client, "/api/v1/epcis/events/batch?mode=partial", {"events": events})

    assert resp.status_code == 207
    [receipt] = receipts
    _assert_receipt(receipt, raw, RECEIPT_ACCEPTED)
    assert receipt["error_summary"] == f"{len(failing)} of {len(events)} events failed"


def test_partial_batch_with_every_event_failing_is_rejected(client, receipts, monkeypatch):
    events = [_event() for _ in range(BATCH_SIZE)]

    def _single(_tenant, event):
        raise HTTPException(status_code=422, detail=event["value"])

    monkeypatch.setattr(router_mod, "_ingest_single_event", _single)
    raw, resp = _post_json(client, "/api/v1/epcis/events/batch?mode=partial", {"events": events})

    assert resp.status_code == 400
    [receipt] = receipts
    _assert_receipt(receipt, raw, RECEIPT_REJECTED)
    assert receipt["error_summary"] == f"{len(events)} of {len(events)} events failed"


def test_empty_batch_files_rejected_receipt(client, receipts):
    raw, resp = _post_json(client, "/api/v1/epcis/events/batch", {"events": []})

    assert resp.status_code == 400
    [receipt] = receipts
    _assert_receipt(receipt, raw, RECEIPT_REJECTED)
    assert receipt["error_summary"] == "HTTPException 400"


# ── XML ──────────────────────────────────────────────────────────────────────


def _post_xml(client: TestClient, raw: bytes, mode: str = "atomic"):
    return client.post(
        f"/api/v1/epcis/events/xml?mode={mode}", content=raw, headers={"Content-Type": "application/xml"}
    )


def test_xml_document_files_accepted_receipt(client, receipts, monkeypatch):
    raw = uuid4().hex.encode()
    events = [_event() for _ in range(BATCH_SIZE)]
    monkeypatch.setattr(router_mod, "_is_xml_content", lambda body: True)
    monkeypatch.setattr(router_mod, "_parse_epcis_xml", lambda body: events)
    monkeypatch.setattr(
        router_mod, "_ingest_batch_events_db_atomic", lambda t, evs: [({"cte_id": str(uuid4())}, 201) for _ in evs]
    )

    assert _post_xml(client, raw).status_code == 201
    [receipt] = receipts
    _assert_receipt(receipt, raw, RECEIPT_ACCEPTED)


def test_xml_without_events_files_rejected_receipt(client, receipts, monkeypatch):
    raw = uuid4().hex.encode()
    monkeypatch.setattr(router_mod, "_is_xml_content", lambda body: True)
    monkeypatch.setattr(router_mod, "_parse_epcis_xml", lambda body: [])

    assert _post_xml(client, raw).status_code == 422
    [receipt] = receipts
    _assert_receipt(receipt, raw, RECEIPT_REJECTED)
    assert receipt["error_summary"] == "HTTPException 422"


def test_non_xml_body_files_rejected_receipt(client, receipts, monkeypatch):
    raw = uuid4().hex.encode()
    monkeypatch.setattr(router_mod, "_is_xml_content", lambda body: False)

    assert _post_xml(client, raw).status_code == 400
    [receipt] = receipts
    _assert_receipt(receipt, raw, RECEIPT_REJECTED)
    assert len(receipt["error_summary"]) <= MAX_ERROR_SUMMARY_LENGTH


def test_invalid_mode_is_rejected_before_the_body_is_read(client, receipts):
    assert _post_xml(client, uuid4().hex.encode(), mode=uuid4().hex).status_code == 400
    assert receipts == []


@pytest.mark.parametrize(
    "counts", [{"failed": str(BATCH_SIZE), "total": BATCH_SIZE}, {"failed": BATCH_SIZE, "total": None}]
)
def test_partial_response_with_non_int_counts_files_no_summary(receipts, counts):
    from fastapi.responses import JSONResponse

    raw = uuid4().hex.encode()
    router_mod._receipt_for_response(TENANT, raw, JSONResponse(counts, status_code=207))

    [receipt] = receipts
    _assert_receipt(receipt, raw, RECEIPT_ACCEPTED)
    assert receipt["error_summary"] is None
