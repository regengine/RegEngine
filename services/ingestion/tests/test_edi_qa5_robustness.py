"""QA5 deep-pass: robustness and boundary tests for ``edi_ingestion``.

Gaps found by reading every file in
``services/ingestion/app/edi_ingestion/`` that existing suites
(``test_edi_ingestion_api``, ``test_edi_wire_format_*``,
``test_edi_envelope_integrity``, ``test_edi_golden``,
``test_edi_rejection_log_1174``, ``test_edi_parser_segment_cap_1171``,
``test_edi_segment_metrics``, ``test_edi_utf8_decode_1170``,
``test_edi_gln_check_digit_consistency``) do not cover:

- malformed single-element segments must fail closed with 4xx, never 500
- 850 ``reference_document_number`` fallback when the PO number arrives
  only via ``REF*PO`` (BEG without a PO number)
- ``X-Partner-ID`` enforcement (``EDI_REQUIRE_PARTNER_ID`` /
  ``EDI_PARTNER_ALLOWLIST``) at the HTTP boundary
- tenant isolation at the HTTP boundary (form-vs-header conflict,
  principal tenant binding)
- interchange dedup 409 at the HTTP boundary
- unbalanced ST/SE framing at the HTTP boundary
- rejection-log ring eviction and tenant scoping under a small cap
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.edi_ingestion.routes as edi_ingestion_routes  # noqa: E402
from app.authz import IngestionPrincipal, get_ingestion_principal  # noqa: E402
from app.edi_ingestion import (
    rejection_log as rejection_log_mod,  # noqa: E402
    router as edi_router,  # noqa: E402
)
from app.edi_ingestion.extractors import _extract_850_fields  # noqa: E402
from app.edi_ingestion.parser import (  # noqa: E402
    _declared_transaction_set_count,
    _parse_x12_segments,
    _split_transaction_sets,
)
from app.edi_ingestion.rejection_log import (  # noqa: E402
    list_edi_rejections,
    record_edi_rejection,
    reset_edi_rejections,
)
from app.webhook_models import EventResult, IngestResponse  # noqa: E402

TEST_TENANT_ID = "00000000-0000-0000-0000-000000000123"
OTHER_TENANT_ID = "00000000-0000-0000-0000-000000000999"
VALID_FSMA_TLC = "00012345678901-LOT001"

# Minimal valid 856. ISA13/IEA control number "000000001" is swapped per
# test via _with_isa13 so replays never collide on envelope identity.
VALID_856 = (
    b"ISA*00*          *00*          *ZZ*SENDERID       *ZZ*RECEIVERID     *260310*1200*U*00401*000000001*0*P*>~"
    b"GS*SH*SENDERID*RECEIVERID*20260310*1200*1*X*004010~"
    b"ST*856*0001~"
    b"BSN*00*ASN-12345*20260310*1200~"
    b"HL*1**S~"
    b"N1*SF*Valley Fresh Farms*92*0614141000005~"
    b"N1*ST*Metro Distribution Center*92*0614141000006~"
    b"LIN**SK*ROMAINE-12CT~"
    b"SN1**200*CA~"
    b"REF*BM*BOL-9001~"
    b"TD5**2*ColdExpress~"
    b"SE*11*0001~"
    b"GE*1*1~"
    b"IEA*1*000000001~"
)


def _with_isa13(raw: bytes, n: int) -> bytes:
    return raw.replace(b"000000001", f"{n:09d}".encode("ascii"))


@pytest.fixture()
def captured_payload() -> dict:
    return {}


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, captured_payload: dict) -> TestClient:
    # Isolate partner-gate env so the developer shell cannot flip these.
    monkeypatch.delenv("EDI_REQUIRE_PARTNER_ID", raising=False)
    monkeypatch.delenv("EDI_PARTNER_ALLOWLIST", raising=False)
    app = FastAPI()
    app.include_router(edi_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key",
        scopes=["*"],
        auth_mode="test",
    )

    async def _fake_ingest_events(payload, *, principal_tenant_id=None, x_regengine_api_key=None):
        captured_payload["payload"] = payload
        event = payload.events[0]
        return IngestResponse(
            accepted=1,
            rejected=0,
            total=1,
            events=[
                EventResult(
                    traceability_lot_code=event.traceability_lot_code,
                    cte_type=event.cte_type.value,
                    status="accepted",
                    event_id="evt-edi-qa5",
                    sha256_hash="hash-1",
                    chain_hash="chain-1",
                )
            ],
        )

    monkeypatch.setattr(edi_ingestion_routes, "ingest_events", _fake_ingest_events)
    # Neutralize ISA13 dedup: unit coverage lives in
    # test_edi_envelope_integrity; here every test controls replay itself.
    monkeypatch.setattr(
        edi_ingestion_routes,
        "check_and_record_interchange",
        lambda *a, **kw: (False, None),
    )
    with TestClient(app) as test_client:
        yield test_client


def _post_legacy(client: TestClient, raw: bytes, **form) -> object:
    data = {"traceability_lot_code": "LOT-QA5-001", "tenant_id": TEST_TENANT_ID}
    data.update(form)
    return client.post(
        "/api/v1/ingest/edi",
        data=data,
        files={"file": ("asn.edi", raw, "application/edi-x12")},
        headers={"X-Partner-ID": "WALMART"},
    )


# ---------------------------------------------------------------------------
# Malformed segments fail closed with 4xx, never 500
# ---------------------------------------------------------------------------


def test_legacy_856_bare_st_returns_400_not_500(client: TestClient) -> None:
    """A single-element ``ST`` segment must not crash the legacy route.

    ``(_first_segment(segments, "ST") or ["", ""])[1]`` indexes ST01
    unconditionally; a bare ``ST~`` segment returns ``["ST"]`` (truthy)
    and ``[1]`` raised ``IndexError`` -> HTTP 500. Fixed to treat a
    missing ST01 as an unsupported transaction set (HTTP 400).
    """
    raw = _with_isa13(VALID_856, 11).replace(b"ST*856*0001~", b"ST~")
    response = _post_legacy(client, raw)
    assert response.status_code == 400
    assert response.json()["detail"] == "Only X12 856 is currently supported"


def test_bare_n1_segment_is_tolerated(client: TestClient, captured_payload: dict) -> None:
    """A single-element ``N1~`` segment is skipped, not fatal.

    Every extractor guards ``segment[1]`` with a length check; this pins
    that contract at the HTTP boundary so a partner's empty N1 can never
    become a 500.
    """
    raw = _with_isa13(VALID_856, 12).replace(
        b"N1*ST*Metro Distribution Center*92*0614141000006~",
        b"N1~N1*ST*Metro Distribution Center*92*0614141000006~",
    )
    response = _post_legacy(client, raw)
    assert response.status_code == 201, response.text
    assert response.json()["extracted"]["ship_to_location"] == "Metro Distribution Center"


def test_empty_payload_returns_400(client: TestClient) -> None:
    response = _post_legacy(client, b"")
    assert response.status_code == 400


def test_non_edi_payload_returns_400(client: TestClient) -> None:
    response = _post_legacy(client, b"this is a csv,lot,quantity\n1,2,3\n")
    assert response.status_code == 400


def test_unbalanced_st_se_rejected_on_document_route(client: TestClient, captured_payload: dict) -> None:
    """An ST without its closing SE is rejected, not parsed by guessing."""
    raw = _with_isa13(VALID_856, 13).replace(b"SE*11*0001~", b"")
    response = client.post(
        "/api/v1/ingest/edi/document",
        data={"traceability_lot_code": VALID_FSMA_TLC, "tenant_id": TEST_TENANT_ID},
        files={"file": ("bad.edi", raw, "application/edi-x12")},
        headers={"X-Partner-ID": "WALMART"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "unbalanced_transaction_sets"
    assert "payload" not in captured_payload


# ---------------------------------------------------------------------------
# 850 reference fallback
# ---------------------------------------------------------------------------


def test_850_reference_falls_back_to_ref_po_number() -> None:
    """When BEG carries no PO number, ``REF*PO`` still sets the reference.

    The extractor snapshotted ``reference_document_number`` from BEG
    before the segment loop, so a PO number arriving only via ``REF*PO``
    updated ``po_number`` but left ``reference_document_number`` as None
    and the CTE lost its document link.
    """
    raw = (
        "ISA*00*          *00*          *ZZ*SENDERID       *ZZ*RECEIVERID     *260310*1200*U*00401*000000014*0*P*>~"
        "GS*PO*SENDERID*RECEIVERID*20260310*1200*1*X*004010~"
        "ST*850*0001~"
        "BEG*00*SA**20260310~"
        "PO1*1*50*CA*12.5*SK*WIDGET-1~"
        "REF*PO*PO-REF-999~"
        "SE*5*0001~"
        "GE*1*1~"
        "IEA*1*000000014~"
    )
    data = _extract_850_fields(_parse_x12_segments(raw))
    assert data["po_number"] == "PO-REF-999"
    assert data["reference_document_number"] == "PO-REF-999"


# ---------------------------------------------------------------------------
# Partner header enforcement at the HTTP boundary
# ---------------------------------------------------------------------------


def test_require_partner_id_rejects_missing_header(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDI_REQUIRE_PARTNER_ID", "true")
    response = client.post(
        "/api/v1/ingest/edi",
        data={"traceability_lot_code": "LOT-QA5-001", "tenant_id": TEST_TENANT_ID},
        files={"file": ("asn.edi", _with_isa13(VALID_856, 21), "application/edi-x12")},
    )
    assert response.status_code == 400
    assert "X-Partner-ID" in response.json()["detail"]


def test_require_partner_id_on_value_is_truthy(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """``EDI_REQUIRE_PARTNER_ID=on`` must enforce, like ``EDI_STRICT_MODE``.

    ``_verify_partner_id`` only accepted ``1/true/yes`` while the sibling
    strict-mode flag also accepts ``on``/``strict``; an operator setting
    ``=on`` believed the gate was closed when it was open.
    """
    monkeypatch.setenv("EDI_REQUIRE_PARTNER_ID", "on")
    response = client.post(
        "/api/v1/ingest/edi",
        data={"traceability_lot_code": "LOT-QA5-001", "tenant_id": TEST_TENANT_ID},
        files={"file": ("asn.edi", _with_isa13(VALID_856, 22), "application/edi-x12")},
    )
    assert response.status_code == 400


def test_partner_allowlist_blocks_unknown_partner(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDI_PARTNER_ALLOWLIST", "WALMART")
    response = client.post(
        "/api/v1/ingest/edi",
        data={"traceability_lot_code": "LOT-QA5-001", "tenant_id": TEST_TENANT_ID},
        files={"file": ("asn.edi", _with_isa13(VALID_856, 23), "application/edi-x12")},
        headers={"X-Partner-ID": "ACME"},
    )
    assert response.status_code == 403


def test_partner_allowlist_permits_listed_partner(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDI_PARTNER_ALLOWLIST", "WALMART, ACME")
    response = _post_legacy(client, _with_isa13(VALID_856, 24))
    assert response.status_code == 201, response.text


# ---------------------------------------------------------------------------
# Tenant isolation at the HTTP boundary
# ---------------------------------------------------------------------------


def test_conflicting_tenant_form_and_header_returns_400(client: TestClient) -> None:
    response = client.post(
        "/api/v1/ingest/edi",
        data={"traceability_lot_code": "LOT-QA5-001", "tenant_id": TEST_TENANT_ID},
        files={"file": ("asn.edi", _with_isa13(VALID_856, 25), "application/edi-x12")},
        headers={"X-Partner-ID": "WALMART", "X-Tenant-ID": OTHER_TENANT_ID},
    )
    assert response.status_code == 400
    assert "Conflicting tenant context" in response.json()["detail"]


def test_principal_tenant_binding_rejects_other_tenant(monkeypatch: pytest.MonkeyPatch, captured_payload: dict) -> None:
    """A tenant-scoped principal cannot ingest into another tenant."""
    monkeypatch.delenv("EDI_REQUIRE_PARTNER_ID", raising=False)
    monkeypatch.delenv("EDI_PARTNER_ALLOWLIST", raising=False)
    app = FastAPI()
    app.include_router(edi_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="tenant-key",
        scopes=["edi.ingest"],
        tenant_id=TEST_TENANT_ID,
        auth_mode="scoped_key",
    )

    async def _fake_ingest_events(payload, *, principal_tenant_id=None, x_regengine_api_key=None):
        captured_payload["payload"] = payload
        event = payload.events[0]
        return IngestResponse(
            accepted=1,
            rejected=0,
            total=1,
            events=[
                EventResult(
                    traceability_lot_code=event.traceability_lot_code,
                    cte_type=event.cte_type.value,
                    status="accepted",
                    event_id="evt-edi-qa5",
                    sha256_hash="hash-1",
                    chain_hash="chain-1",
                )
            ],
        )

    monkeypatch.setattr(edi_ingestion_routes, "ingest_events", _fake_ingest_events)
    monkeypatch.setattr(edi_ingestion_routes, "check_and_record_interchange", lambda *a, **kw: (False, None))
    with TestClient(app) as bound_client:
        denied = bound_client.post(
            "/api/v1/ingest/edi",
            data={"traceability_lot_code": "LOT-QA5-001", "tenant_id": OTHER_TENANT_ID},
            files={"file": ("asn.edi", _with_isa13(VALID_856, 26), "application/edi-x12")},
            headers={"X-Partner-ID": "WALMART"},
        )
        assert denied.status_code == 403
        assert "payload" not in captured_payload

        captured_payload.clear()
        allowed = bound_client.post(
            "/api/v1/ingest/edi",
            data={"traceability_lot_code": "LOT-QA5-001", "tenant_id": TEST_TENANT_ID},
            files={"file": ("asn.edi", _with_isa13(VALID_856, 27), "application/edi-x12")},
            headers={"X-Partner-ID": "WALMART"},
        )
        assert allowed.status_code == 201, allowed.text
        assert allowed.json()["sender_tenant_id"] == TEST_TENANT_ID


# ---------------------------------------------------------------------------
# Dedup replay at the HTTP boundary
# ---------------------------------------------------------------------------


def test_duplicate_interchange_returns_409_idempotent_replay(
    client: TestClient, captured_payload: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        edi_ingestion_routes,
        "check_and_record_interchange",
        lambda *a, **kw: (True, "seen"),
    )
    response = _post_legacy(client, _with_isa13(VALID_856, 28))
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "duplicate_interchange"
    assert detail["idempotent_replay"] is True
    assert "payload" not in captured_payload


# ---------------------------------------------------------------------------
# Parser unit pins: multi-GE count, stray segments
# ---------------------------------------------------------------------------


def test_declared_count_sums_across_functional_groups() -> None:
    segments = _parse_x12_segments(
        "ISA*00*          *00*          *ZZ*SENDERID       *ZZ*RECEIVERID     *260310*1200*U*00401*000000029*0*P*>~"
        "GS*SH*S*R*20260310*1200*1*X*004010~"
        "ST*856*0001~SE*2*0001~"
        "GE*2*1~"
        "GS*SH*S*R*20260310*1200*2*X*004010~"
        "ST*856*0002~SE*2*0002~"
        "GE*3*2~"
        "IEA*2*000000029~"
    )
    assert _declared_transaction_set_count(segments) == 5


def test_declared_count_skips_unparseable_ge01() -> None:
    segments = _parse_x12_segments(
        "ISA*00*          *00*          *ZZ*SENDERID       *ZZ*RECEIVERID     *260310*1200*U*00401*000000030*0*P*>~"
        "GS*SH*S*R*20260310*1200*1*X*004010~"
        "ST*856*0001~SE*2*0001~"
        "GE*X*1~"
        "IEA*1*000000030~"
    )
    assert _declared_transaction_set_count(segments) is None


def test_split_drops_stray_body_segments_between_transaction_sets() -> None:
    """Body segments outside any ST/SE pair belong to no transaction set."""
    segments = _parse_x12_segments(
        "ISA*00*          *00*          *ZZ*SENDERID       *ZZ*RECEIVERID     *260310*1200*U*00401*000000031*0*P*>~"
        "GS*SH*S*R*20260310*1200*1*X*004010~"
        "ST*856*0001~SN1**120*CA~SE*3*0001~"
        "SN1**999*CA~"
        "ST*856*0002~SN1**240*CA~SE*3*0002~"
        "GE*2*1~"
        "IEA*1*000000031~"
    )
    slices = _split_transaction_sets(segments)
    assert len(slices) == 2
    quantities = []
    for sl in slices:
        quantities.extend(part[2] for part in sl if part and part[0] == "SN1")
    assert quantities == ["120", "240"]


# ---------------------------------------------------------------------------
# Rejection-log ring behavior
# ---------------------------------------------------------------------------


def test_rejection_log_evicts_oldest_at_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rejection_log_mod, "_EDI_REJECTION_CAP_PER_TENANT", 2)
    reset_edi_rejections()
    first = record_edi_rejection(
        tenant_id=TEST_TENANT_ID,
        transaction_set="856",
        traceability_lot_code="LOT-1",
        errors=[{"msg": "bad"}],
    )
    record_edi_rejection(
        tenant_id=TEST_TENANT_ID,
        transaction_set="856",
        traceability_lot_code="LOT-2",
        errors=[{"msg": "bad"}],
    )
    record_edi_rejection(
        tenant_id=TEST_TENANT_ID,
        transaction_set="856",
        traceability_lot_code="LOT-3",
        errors=[{"msg": "bad"}],
    )
    kept = list_edi_rejections(TEST_TENANT_ID)
    assert len(kept) == 2
    assert first["rejection_id"] not in {r["rejection_id"] for r in kept}
    assert [r["traceability_lot_code"] for r in kept] == ["LOT-2", "LOT-3"]
    reset_edi_rejections()


def test_rejection_ids_are_unique_per_record() -> None:
    reset_edi_rejections()
    try:
        ids = {
            record_edi_rejection(
                tenant_id=TEST_TENANT_ID,
                transaction_set="856",
                traceability_lot_code=f"LOT-{i}",
                errors=[{"msg": "bad"}],
            )["rejection_id"]
            for i in range(5)
        }
        assert len(ids) == 5
    finally:
        reset_edi_rejections()
