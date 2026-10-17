"""X12 944 and 945 warehouse advices on the unified EDI document route.

944 (Warehouse Stock Transfer Receipt Advice) is a receiving CTE.
945 (Warehouse Shipping Advice) is a shipping CTE. Both use the same
validation, envelope checks, interchange dedup, and persistence path
as 861 and 856. An unrecognized set still returns the same 400.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.edi_ingestion.routes as edi_ingestion_routes  # noqa: E402
from app.authz import IngestionPrincipal, get_ingestion_principal  # noqa: E402
from app.edi_ingestion import router as edi_router  # noqa: E402
from app.edi_ingestion.extractors import _extract_fields_for_set  # noqa: E402
from app.edi_ingestion.parser import _parse_x12_segments  # noqa: E402
from app.edi_ingestion.transaction_sets import _SUPPORTED_TRANSACTION_SETS  # noqa: E402
from app.webhook_models import EventResult, IngestResponse, WebhookCTEType  # noqa: E402

_CORPUS_DIR = Path(__file__).parent / "fixtures" / "edi_corpus"
TEST_TENANT_ID = "00000000-0000-0000-0000-000000000123"
_VALID_FSMA_TLC = "00012345678901-LOT001"


@pytest.fixture()
def captured_payload() -> dict:
    return {}


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, captured_payload: dict) -> TestClient:
    monkeypatch.setenv("EDI_STRICT_MODE", "true")
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
        captured_payload["calls"] = captured_payload.get("calls", 0) + 1
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
                    event_id="evt-edi-warehouse",
                    sha256_hash="hash-1",
                    chain_hash="chain-1",
                )
            ],
        )

    monkeypatch.setattr(edi_ingestion_routes, "ingest_events", _fake_ingest_events)
    monkeypatch.setattr(
        edi_ingestion_routes,
        "check_and_record_interchange",
        lambda *a, **kw: (False, None),
    )
    with TestClient(app) as test_client:
        yield test_client


def _post(client: TestClient, raw: bytes, *, name: str, strict: bool | None = None):
    params = None if strict is None else {"strict": "true" if strict else "false"}
    return client.post(
        "/api/v1/ingest/edi/document",
        params=params,
        data={
            "traceability_lot_code": _VALID_FSMA_TLC,
            "tenant_id": TEST_TENANT_ID,
        },
        files={"file": (name, raw, "application/edi-x12")},
        headers={"X-Partner-ID": "WALMART"},
    )


def test_golden_944_receiving_event_populates_kdes(client: TestClient, captured_payload: dict) -> None:
    """A warehouse receipt becomes a receiving CTE with lot, quantity, UOM, date, and location."""
    raw = (_CORPUS_DIR / "receipt_944.edi").read_bytes()
    response = _post(client, raw, name="receipt_944.edi")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["document_type"] == "X12_944"
    assert body["extracted"]["fsma_validation_status"] == "passed"
    assert body["ingestion_result"]["accepted"] == 1

    event = captured_payload["payload"].events[0]
    assert event.cte_type == WebhookCTEType.RECEIVING
    assert event.quantity == 120.0
    assert event.unit_of_measure == "cases"
    assert event.product_description == "Romaine Hearts 12ct"
    assert event.location_name == "Metro Distribution Center"
    assert event.location_gln == "6141410000069"
    assert event.kdes["event_date"] == "2026-03-18"
    assert event.kdes["lot_number"] == "LOT-ROM-18"
    assert event.kdes["receiving_location"] == "Metro Distribution Center"
    assert event.kdes["ship_from_location"] == "Valley Fresh Farms"
    assert event.kdes["reference_document_number"] == "WR-944001"
    assert event.traceability_lot_code == _VALID_FSMA_TLC


def test_golden_945_shipping_event_populates_ship_from_and_ship_to(client: TestClient, captured_payload: dict) -> None:
    """A warehouse shipping advice becomes a shipping CTE with both parties."""
    raw = (_CORPUS_DIR / "advice_945.edi").read_bytes()
    response = _post(client, raw, name="advice_945.edi")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["document_type"] == "X12_945"
    assert body["extracted"]["fsma_validation_status"] == "passed"

    event = captured_payload["payload"].events[0]
    assert event.cte_type == WebhookCTEType.SHIPPING
    # W1203 (units shipped) is 120. W1202 (ordered) is 80 and must not win.
    assert event.quantity == 120.0
    assert event.unit_of_measure == "cases"
    assert event.kdes["event_date"] == "2026-03-19"
    assert event.kdes["ship_from_location"] == "Metro Distribution Center"
    assert event.kdes["ship_to_location"] == "Harbor Market"
    assert event.kdes["ship_from_gln"] == "6141410000069"
    assert event.kdes["ship_to_gln"] == "6141410000014"
    assert event.location_gln == "6141410000069"
    assert event.kdes["lot_number"] == "LOT-ROM-19"
    # Qualifier 92 is an assigned id, not a GLN, so the depositor id stays
    # off the GLN fields.
    assert event.kdes["depositor_name"] == "Valley Fresh Farms"
    assert event.kdes["depositor_id"] == "DEP-100"
    assert "depositor_gln" not in event.kdes


def test_944_header_date_wins_over_g62_and_lot_can_come_from_n9() -> None:
    """W17 date is the receipt date. A lot that exists only on N9*LT is still read."""
    raw = (_CORPUS_DIR / "receipt_944.edi").read_text(encoding="utf-8")
    without_w07_lot = raw.replace("***LOT-ROM-18", "").replace("N9*LT*LOT-ROM-18~", "")
    # The corpus file still has N9*LT. This copy drops the W07 lot element
    # only, so the N9 qualifier is the remaining source.
    n9_only = raw.replace("***LOT-ROM-18", "")
    extracted = _extract_fields_for_set("944", _parse_x12_segments(n9_only))
    assert extracted["lot_number"] == "LOT-ROM-18"
    assert extracted["receive_date_raw"] == "20260318"
    assert extracted["g62_date_raw"] == "20260317"
    assert extracted["gtin"] == "00012345678905"
    assert extracted["upc"] == "012345678905"
    assert extracted["warehouse_gln"] == "6141410000069"
    assert extracted["depositor_gln"] == "6141410000014"

    no_lot = _extract_fields_for_set("944", _parse_x12_segments(without_w07_lot))
    assert no_lot["lot_number"] is None
    assert no_lot["quantity"] == 120.0


def test_945_shipped_quantity_ignores_ordered_and_non_gln_qualifier() -> None:
    raw = (_CORPUS_DIR / "advice_945.edi").read_text(encoding="utf-8")
    extracted = _extract_fields_for_set("945", _parse_x12_segments(raw))
    assert extracted["quantity"] == 120.0
    assert extracted["quantity_ordered"] == 80.0
    assert extracted["ship_date_raw"] == "20260319"
    assert extracted["g62_date_raw"] == "20260318"
    assert extracted["ship_from_name"] == "Metro Distribution Center"
    assert extracted["ship_from_gln"] == "6141410000069"
    assert extracted["ship_to_name"] == "Harbor Market"
    assert extracted["ship_to_gln"] == "6141410000014"
    assert extracted["depositor_id"] == "DEP-100"
    assert extracted["depositor_gln"] is None
    assert extracted["po_number"] == "PO-8801"
    assert extracted["reference_document_number"] == "SID-945001"
    assert extracted["lot_number"] == "LOT-ROM-19"


def _receipt_missing_lot() -> bytes:
    raw = (_CORPUS_DIR / "receipt_944.edi").read_text(encoding="utf-8")
    edited = raw.replace("***LOT-ROM-18", "").replace("N9*LT*LOT-ROM-18~", "")
    # Dropping one segment leaves SE01 stale. The parser does not check
    # SE01, and the document still has its W17 header.
    return edited.encode("utf-8")


def _receipt_missing_quantity() -> bytes:
    raw = (_CORPUS_DIR / "receipt_944.edi").read_text(encoding="utf-8")
    edited = raw.replace("W07*120*CA*012345678905*UK*00012345678905***LOT-ROM-18~", "")
    return edited.encode("utf-8")


def test_944_strict_missing_lot_returns_422_and_persists_nothing(client: TestClient, captured_payload: dict) -> None:
    from app.edi_ingestion.rejection_log import list_edi_rejections, reset_edi_rejections

    reset_edi_rejections()
    captured_payload.clear()
    response = _post(client, _receipt_missing_lot(), name="receipt_944_no_lot.edi", strict=True)
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "fsma_validation_failed"
    assert detail["transaction_set"] == "944"
    locs = [tuple(err.get("loc") or ()) for err in detail["errors"]]
    assert any("lot_number" in loc for loc in locs)
    assert "payload" not in captured_payload
    rejections = list_edi_rejections(TEST_TENANT_ID)
    assert len(rejections) == 1
    assert rejections[0]["reason"] == "fsma_validation_failed"
    assert rejections[0]["transaction_set"] == "944"


def test_944_strict_missing_quantity_returns_422_and_persists_nothing(
    client: TestClient, captured_payload: dict
) -> None:
    from app.edi_ingestion.rejection_log import list_edi_rejections, reset_edi_rejections

    reset_edi_rejections()
    captured_payload.clear()
    response = _post(client, _receipt_missing_quantity(), name="receipt_944_no_qty.edi", strict=True)
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "fsma_validation_failed"
    assert detail["transaction_set"] == "944"
    locs = [tuple(err.get("loc") or ()) for err in detail["errors"]]
    assert any("quantity" in loc for loc in locs)
    assert "payload" not in captured_payload
    rejections = list_edi_rejections(TEST_TENANT_ID)
    assert len(rejections) == 1
    assert rejections[0]["transaction_set"] == "944"


def test_944_advisory_missing_lot_writes_rejection_log(client: TestClient, captured_payload: dict) -> None:
    """Advisory mode records the rejection and does not call the canonical ingest path."""
    from app.edi_ingestion.rejection_log import list_edi_rejections, reset_edi_rejections

    reset_edi_rejections()
    captured_payload.clear()
    response = _post(client, _receipt_missing_lot(), name="receipt_944_no_lot.edi", strict=False)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "rejected"
    assert body["document_type"] == "X12_944"
    assert body["extracted"]["fsma_validation_status"] == "failed"
    assert body["ingestion_result"] is None
    rejection = body["rejection"]
    assert rejection["reason"] == "fsma_validation_failed"
    assert rejection["rejection_id"].startswith("edi-rej-")
    assert "payload" not in captured_payload

    rejections = list_edi_rejections(TEST_TENANT_ID)
    assert len(rejections) == 1
    recorded = rejections[0]
    assert recorded["rejection_id"] == rejection["rejection_id"]
    assert recorded["transaction_set"] == "944"
    assert recorded["traceability_lot_code"] == _VALID_FSMA_TLC
    assert recorded["partner_id"] == "WALMART"


@pytest.mark.parametrize("name", ["receipt_944.edi", "advice_945.edi"])
def test_warehouse_envelope_mismatch_matches_856(client: TestClient, captured_payload: dict, name: str) -> None:
    raw = (_CORPUS_DIR / name).read_text(encoding="utf-8")
    mismatched = raw.replace("GS*RE*SENDERID*", "GS*RE*OTHERSENDER*", 1).replace(
        "GS*SW*SENDERID*", "GS*SW*OTHERSENDER*", 1
    )
    assert mismatched != raw
    captured_payload.clear()
    response = _post(client, mismatched.encode("utf-8"), name=name)
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "edi_envelope_mismatch"
    assert detail["isa_sender_id"] == "SENDERID"
    assert detail["gs_sender_id"] == "OTHERSENDER"
    assert "payload" not in captured_payload


@pytest.mark.parametrize(
    ("name", "isa13"),
    [("receipt_944.edi", "000000944"), ("advice_945.edi", "000000945")],
)
def test_warehouse_isa13_replay_matches_856(
    client: TestClient,
    captured_payload: dict,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    isa13: str,
) -> None:
    seen: dict[str, str | None] = {}

    def _duplicate(sender_id, receiver_id, isa13):
        seen["sender_id"] = sender_id
        seen["receiver_id"] = receiver_id
        seen["isa13"] = isa13
        return (True, "seen")

    monkeypatch.setattr(edi_ingestion_routes, "check_and_record_interchange", _duplicate)
    captured_payload.clear()
    raw = (_CORPUS_DIR / name).read_bytes()
    response = _post(client, raw, name=name)
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "duplicate_interchange"
    assert detail["idempotent_replay"] is True
    assert detail["isa13"] == isa13
    assert seen["isa13"] == isa13
    assert seen["sender_id"] == "SENDERID"
    assert seen["receiver_id"] == "RECEIVERID"
    assert "payload" not in captured_payload


def test_944_does_not_sum_quantities_across_different_units() -> None:
    """CA and CS are both cases, so they sum. Cases and pounds do not."""
    raw = (_CORPUS_DIR / "receipt_944.edi").read_text(encoding="utf-8")
    w07 = "W07*120*CA*012345678905*UK*00012345678905***LOT-ROM-18~"
    equivalent = raw.replace(
        w07,
        "W07*80*CS*012345678905*UK*00012345678905***LOT-ROM-18~W07*40*CA*012345678905*UK*00012345678905***LOT-ROM-18~",
    )
    extracted = _extract_fields_for_set("944", _parse_x12_segments(equivalent))
    assert extracted["quantity"] == 120.0
    assert extracted["unit_of_measure"] == "CS"

    mixed = raw.replace(
        "G69*Romaine Hearts 12ct~",
        "W07*40*LB*012345678905*UK*00012345678905***LOT-ROM-18~G69*Romaine Hearts 12ct~",
    )
    with pytest.raises(HTTPException) as exc:
        _extract_fields_for_set("944", _parse_x12_segments(mixed))
    assert exc.value.status_code == 422
    assert exc.value.detail["error"] == "edi_944_mixed_units_of_measure"


def test_unknown_transaction_set_keeps_the_same_error(client: TestClient, captured_payload: dict) -> None:
    raw = (_CORPUS_DIR / "receipt_944.edi").read_bytes().replace(b"ST*944*", b"ST*943*")
    captured_payload.clear()
    response = _post(client, raw, name="unknown.edi")
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert detail == (f"Unsupported or unrecognized transaction set. Supported: {sorted(_SUPPORTED_TRANSACTION_SETS)}")
    assert detail.startswith("Unsupported or unrecognized transaction set. Supported:")
    assert "943" not in detail
    for code in ("810", "850", "856", "861", "944", "945"):
        assert code in detail
    assert "payload" not in captured_payload
