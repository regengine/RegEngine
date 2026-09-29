"""EDI source retention and completed-interchange cache boundaries; no network."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from app.authz import IngestionPrincipal, get_ingestion_principal
from app.edi_ingestion import dedup, routes
from app.webhook_models import EventResult, IngestResponse
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

TENANT_A = "00000000-0000-4000-8000-000000000001"
TENANT_B = "00000000-0000-4000-8000-000000000002"
CORPUS = Path(__file__).parent / "fixtures" / "edi_corpus"
ENDPOINTS = ("/api/v1/ingest/edi", "/api/v1/ingest/edi/document")


class _Redis:
    def __init__(self):
        self.values = {}
        self.actions = []

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, *, nx=False, ex=None):
        self.actions.append("marker")
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True


@pytest.fixture
def harness(monkeypatch):
    cache = _Redis()
    state = SimpleNamespace(cache=cache, calls=[], reject=0, failure=None)
    monkeypatch.setattr(dedup, "_redis_client", lambda: cache)
    monkeypatch.setattr(routes, "verify_trading_partner_allowed", lambda **kwargs: True)
    monkeypatch.delenv("EDI_PARTNER_ALLOWLIST", raising=False)

    async def ingest(payload, *, principal_tenant_id, x_regengine_api_key=None, source_file=None):
        state.calls.append((payload, principal_tenant_id, source_file))
        cache.actions.append("ingest")
        if state.failure:
            raise HTTPException(status_code=503, detail="Synthetic persistence unavailable")
        results = [
            EventResult(
                traceability_lot_code=event.traceability_lot_code,
                cte_type=event.cte_type.value,
                status="rejected" if index < state.reject else "accepted",
            )
            for index, event in enumerate(payload.events)
        ]
        cache.actions.append("commit")
        return IngestResponse(
            accepted=len(results) - state.reject,
            rejected=state.reject,
            total=len(results),
            events=results,
            ingestion_run_id="00000000-0000-4000-8000-000000000003" if source_file else None,
        )

    monkeypatch.setattr(routes, "ingest_events", ingest)
    app = FastAPI()
    app.include_router(routes.router)

    def principal(request: Request):
        return IngestionPrincipal(
            key_id="synthetic-key-id", scopes=["*"], auth_mode="test", tenant_id=request.headers["X-Test-Tenant"]
        )

    app.dependency_overrides[get_ingestion_principal] = principal
    with TestClient(app) as client:
        state.client = client
        yield state


def _post(harness, endpoint, *, tenant=TENANT_A, raw=None, **data):
    return harness.client.post(
        endpoint,
        files={"file": ("original.edi", raw or (CORPUS / "asn_856.edi").read_bytes(), "application/edi-x12")},
        data={"traceability_lot_code": "00012345678901-LOT001", **data},
        headers={"X-Test-Tenant": tenant},
    )


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_edi_retains_exact_source_bytes_in_tenant_receipt(harness, endpoint):
    raw = (CORPUS / "asn_856.edi").read_bytes().replace(b"Valley Fresh Farms", b"Valley Fresh Farm\xe9")
    response = _post(harness, endpoint, raw=raw, source="custom-partner-feed")
    assert response.status_code == 201, response.text
    payload, tenant, receipt = harness.calls[0]
    assert receipt is not None, "EDI accepted without retaining its source file"
    assert tenant == TENANT_A and payload.tenant_id == TENANT_A
    assert receipt.raw_bytes == raw and receipt.sha256 == hashlib.sha256(raw).hexdigest()
    assert receipt.filename == "original.edi" and receipt.content_type == "application/edi-x12"
    assert receipt.initiated_by == "synthetic-key-id" and receipt.record_count == 1
    assert getattr(receipt, "source_system", None) == "edi"
    assert response.json()["ingestion_result"]["ingestion_run_id"] is not None


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_same_interchange_is_independent_between_tenants(harness, endpoint):
    assert _post(harness, endpoint).status_code == 201
    assert _post(harness, endpoint, tenant=TENANT_B).status_code == 201
    assert [call[1] for call in harness.calls] == [TENANT_A, TENANT_B]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_failed_persistence_leaves_interchange_retryable(harness, endpoint):
    harness.failure = True
    assert _post(harness, endpoint).status_code == 503
    assert harness.cache.values == {}, "A failed transaction must not mark the interchange completed"
    harness.failure = None
    assert _post(harness, endpoint).status_code == 201


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_canonical_rejection_leaves_interchange_retryable(harness, endpoint):
    harness.reject = 1
    assert _post(harness, endpoint).status_code == 422
    assert harness.cache.values == {}
    harness.reject = 0
    assert _post(harness, endpoint).status_code == 201


def test_partial_batch_retains_whole_source_and_remains_retryable(harness):
    raw = (CORPUS / "asn_856_batch.edi").read_bytes()
    harness.reject = 1
    response = _post(harness, ENDPOINTS[1], raw=raw)
    assert response.status_code == 207, response.text
    assert harness.cache.values == {}
    payload, _, receipt = harness.calls[0]
    assert receipt is not None and receipt.raw_bytes == raw
    assert receipt.record_count == len(payload.events) == 3
    harness.reject = 0
    assert _post(harness, ENDPOINTS[1], raw=raw).status_code == 201


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_completed_marker_is_written_after_ingestion_commit(harness, endpoint):
    assert _post(harness, endpoint).status_code == 201
    assert harness.cache.actions == ["ingest", "commit", "marker"]
    assert _post(harness, endpoint).status_code == 409
    assert len(harness.calls) == 1


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_forged_tenant_does_not_claim_receipt_or_interchange(harness, endpoint):
    assert _post(harness, endpoint, tenant_id=TENANT_B).status_code == 403
    assert harness.calls == [] and harness.cache.values == {}


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_redis_unavailable_does_not_prevent_durable_ingestion(harness, endpoint, monkeypatch):
    monkeypatch.setattr(dedup, "_redis_client", lambda: None)
    assert _post(harness, endpoint).status_code == 201
    assert harness.calls[0][2] is not None


def test_redis_failures_do_not_log_backend_exception_contents(harness, monkeypatch, caplog):
    class BrokenRedis:
        def get(self, *args, **kwargs):
            raise RuntimeError("private-synthetic-backend-detail")

        set = get

    monkeypatch.setattr(dedup, "_redis_client", lambda: BrokenRedis())
    assert _post(harness, ENDPOINTS[0]).status_code == 201
    assert "private-synthetic-backend-detail" not in caplog.text


def test_pre_ingestion_checks_do_not_reserve_concurrent_interchanges(harness):
    extracted = {"sender_id": "sender", "receiver_id": "receiver", "isa13": "123"}
    for _ in range(2):
        try:
            routes._enforce_envelope_integrity(extracted, TENANT_A, "856")
        except HTTPException as exc:
            pytest.fail(f"Uncommitted concurrent request was blocked: {exc.status_code}")
    assert harness.cache.values == {}


def test_receipt_source_override_uses_existing_edi_run_enum(monkeypatch):
    from app.webhook_compat import SourceFileReceipt, _open_ingestion_run
    from shared.canonical_persistence import CanonicalEventStore

    runs = []

    def create_run(self, run):
        runs.append(run)
        return str(run.id)

    monkeypatch.setattr(CanonicalEventStore, "create_ingestion_run", create_run)
    receipt = SourceFileReceipt(filename="original.edi", raw_bytes=b"synthetic")
    receipt.source_system = "edi"
    session = MagicMock()
    _open_ingestion_run(session, TENANT_A, "custom-partner-feed", receipt)
    assert runs[0].source_system.value == "edi"
    assert str(runs[0].tenant_id) == TENANT_A
    assert session.execute.call_args.args[1]["raw_bytes"] == b"synthetic"


def test_source_receipt_links_do_not_change_event_replay_identity():
    from shared.canonical_event import normalize_webhook_event

    event = SimpleNamespace(
        cte_type="shipping",
        traceability_lot_code="LOT1",
        product_description="Synthetic",
        quantity=1,
        unit_of_measure="kg",
        timestamp="2026-09-01T00:00:00Z",
        location_gln=None,
        location_name="Synthetic dock",
        kdes={},
    )
    original = normalize_webhook_event(event, TENANT_A)
    linked = original.model_copy(update={"ingestion_run_id": uuid4(), "source_file_id": uuid4()})
    assert original.compute_idempotency_key() == linked.compute_idempotency_key()
    assert original.compute_sha256_hash() == linked.compute_sha256_hash()
