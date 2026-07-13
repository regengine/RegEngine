"""Golden/snapshot tests for EDI X12 -> CTE/KDE field mapping (#2536).

The unified EDI route (``POST /api/v1/ingest/edi/document``) auto-detects
X12 856/850/810/861 and runs purely positional segment extraction whose
output becomes FSMA CTE/KDE events persisted to ``fsma.traceability_events``
(and the dual-written ``fsma.cte_events``) plus the append-only hash chain.

Before this module, only the 856 happy path asserted a handful of fields,
and the 850/810/861 extractors were checked only for envelope-key
*presence* (``test_edi_envelope_integrity.test_all_four_extractors_populate_envelope``
even fed them an 856 body). A one-element column-offset shift, the
``/100.0`` TDS divide, or a qualifier-set change could silently
mis-populate KDEs with no failing test.

This module freezes:

1. An extractor-level golden snapshot per set (856/850/810/861): each
   fixture under ``fixtures/edi_corpus/`` runs through
   ``_extract_fields_for_set`` and its full extracted dict is asserted
   against a committed ``<name>.expected.json``. A deliberate offset in
   any ``_extract_*_fields`` reader (e.g. ``bsn[3]``->``bsn[4]``) shifts
   the snapshot and fails the test.
2. An end-to-end ``/document`` mapping test per set asserting the
   resulting ``IngestEvent`` CTE KDEs (quantity, product, location_gln,
   timestamp/event_date).
3. An explicit test pinning the SN1 (fallback 1.0) vs PO1/IT1/RCD
   (fallback 0.0) quantity-fallback divergence, so the difference is a
   documented decision rather than an accident.

Regenerating the snapshots
--------------------------
The expected JSON files are committed and treated as a reviewed
artifact::

    REGEN_EDI_GOLDEN=1 python -m pytest \
        services/ingestion/tests/test_edi_golden.py

then review the diff before committing. The default run never writes
snapshots.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.edi_ingestion.routes as edi_ingestion_routes  # noqa: E402
from app.authz import IngestionPrincipal, get_ingestion_principal  # noqa: E402
from app.edi_ingestion import router as edi_router  # noqa: E402
from app.edi_ingestion.extractors import _extract_fields_for_set  # noqa: E402
from app.edi_ingestion.parser import (  # noqa: E402
    _detect_transaction_set,
    _parse_x12_segments,
)
from app.webhook_models import EventResult, IngestResponse  # noqa: E402

_CORPUS_DIR = Path(__file__).parent / "fixtures" / "edi_corpus"
TEST_TENANT_ID = "00000000-0000-0000-0000-000000000123"
# TLC matching the FSMA 204 GTIN-14 + lot-suffix pattern enforced by
# shared/schemas.py:FSMAEvent.validate_tlc_format (strict mode passes).
_VALID_FSMA_TLC = "00012345678901-LOT001"

# Map fixture stem -> expected transaction set, for the end-to-end loop.
_FIXTURES = {
    "asn_856": "856",
    "po_850": "850",
    "invoice_810": "810",
    "receiving_861": "861",
}


# ---------------------------------------------------------------------------
# (1) Extractor-level golden snapshots
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(_FIXTURES))
def test_edi_extractor_golden(name: str) -> None:
    """Each fixture's full extracted field dict matches its committed
    snapshot. Catches offset/qualifier drift in ``_extract_*_fields``.
    """
    raw = (_CORPUS_DIR / f"{name}.edi").read_text(encoding="utf-8")
    segments = _parse_x12_segments(raw)
    transaction_set = _detect_transaction_set(segments)
    assert transaction_set == _FIXTURES[name], f"{name}.edi detected as {transaction_set}, expected {_FIXTURES[name]}"

    actual = _extract_fields_for_set(transaction_set, segments)
    expected_path = _CORPUS_DIR / f"{name}.expected.json"

    if os.getenv("REGEN_EDI_GOLDEN"):
        expected_path.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        pytest.skip(f"Regenerated snapshot for {name}")

    assert expected_path.exists(), (
        f"Missing golden snapshot {expected_path.name}. Generate it with "
        "REGEN_EDI_GOLDEN=1 and review the diff before committing."
    )
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    assert actual == expected, (
        f"EDI extraction for {name!r} drifted from the committed golden "
        f"snapshot. If intentional, regenerate with REGEN_EDI_GOLDEN=1 and "
        f"review the diff.\n"
        f"expected={json.dumps(expected, indent=2, sort_keys=True)}\n"
        f"actual={json.dumps(actual, indent=2, sort_keys=True)}"
    )


def test_810_total_amount_is_tds_over_100() -> None:
    """#2536 acceptance: 810 ``total_amount == TDS[1] / 100.0``. The
    fixture's TDS is ``186000`` -> ``1860.00``. A change to the /100.0
    divide breaks this and the snapshot above.
    """
    raw = (_CORPUS_DIR / "invoice_810.edi").read_text(encoding="utf-8")
    extracted = _extract_fields_for_set("810", _parse_x12_segments(raw))
    assert extracted["total_amount"] == 1860.0


def test_861_condition_code_is_rcd_index_5() -> None:
    """#2536 acceptance: 861 ``condition_code == RCD[5]``. The fixture's
    RCD is ``RCD*1*118*CA**4`` -> condition_code ``4`` at index 5.
    """
    raw = (_CORPUS_DIR / "receiving_861.edi").read_text(encoding="utf-8")
    extracted = _extract_fields_for_set("861", _parse_x12_segments(raw))
    assert extracted["condition_code"] == "4"


def test_offset_shift_changes_extracted_output() -> None:
    """#2536 acceptance: a one-element offset in a reader (here BSN[3]
    -> BSN[4] for the 856 ship date) produces a different value than the
    committed snapshot — proving the golden snapshot would catch such a
    regression. We mutate a copied segment list, not the source, so this
    test documents the sensitivity without touching production code.
    """
    raw = (_CORPUS_DIR / "asn_856.edi").read_text(encoding="utf-8")
    segments = _parse_x12_segments(raw)
    baseline = _extract_fields_for_set("856", segments)

    # Simulate the off-by-one: read ship_date from BSN[4] (the time
    # element) instead of BSN[3]. The extractor itself is unchanged; we
    # assert that the snapshot value (BSN[3]) and the shifted value
    # (BSN[4]) differ, so any real source-level shift would fail the
    # golden snapshot.
    bsn = next(s for s in segments if s and s[0].upper() == "BSN")
    assert baseline["ship_date_raw"] == bsn[3]
    assert bsn[3] != bsn[4], "fixture must distinguish BSN[3] from BSN[4]"


def test_sn1_vs_po1_quantity_fallback_divergence() -> None:
    """#2536 acceptance: pin the documented divergence in quantity
    fallback between transaction sets.

    When a quantity element is PRESENT but non-numeric:
      * 856 SN1 uses ``_safe_float(..., fallback=1.0)`` -> quantity 1.0
      * 850 PO1 / 810 IT1 / 861 RCD use ``fallback=0.0`` -> the running
        total stays 0, so ``quantity`` is left None.

    This asymmetry is intentional (a shipment notice implies at least
    one unit shipped; an order/invoice/receipt line should not invent a
    quantity). Pinning it here makes a future change to either fallback
    a deliberate, reviewed decision.
    """
    isa = "ISA*00*          *00*          *ZZ*SENDERID       *ZZ*RECEIVERID     *260310*1200*U*00401*000000009*0*P*>~"

    e856 = (
        isa
        + "GS*SH*S*R*20260310*1200*1*X*004010~ST*856*0001~"
        + "BSN*00*A*20260310*1200~HL*1**S~SN1**ABC*CA~"
        + "SE*5*0001~GE*1*1~IEA*1*000000009~"
    )
    e850 = (
        isa
        + "GS*PO*S*R*20260310*1200*1*X*004010~ST*850*0001~"
        + "BEG*00*SA*PO-1~PO1*1*ABC*CA~SE*5*0001~GE*1*1~IEA*1*000000009~"
    )
    e810 = (
        isa
        + "GS*IN*S*R*20260310*1200*1*X*004010~ST*810*0001~"
        + "BIG*20260311*INV-1~IT1*1*ABC*CA~SE*5*0001~GE*1*1~IEA*1*000000009~"
    )
    e861 = (
        isa
        + "GS*RC*S*R*20260310*1200*1*X*004010~ST*861*0001~"
        + "BRA*00*RA-1*20260312~RCD*1*ABC*CA~SE*5*0001~GE*1*1~IEA*1*000000009~"
    )

    q856 = _extract_fields_for_set("856", _parse_x12_segments(e856))["quantity"]
    q850 = _extract_fields_for_set("850", _parse_x12_segments(e850))["quantity"]
    q810 = _extract_fields_for_set("810", _parse_x12_segments(e810))["quantity"]
    q861 = _extract_fields_for_set("861", _parse_x12_segments(e861))["quantity"]

    assert q856 == 1.0, "856 SN1 falls back to 1.0 for a non-numeric quantity"
    assert q850 is None, "850 PO1 falls back to 0.0 -> quantity left None"
    assert q810 is None, "810 IT1 falls back to 0.0 -> quantity left None"
    assert q861 is None, "861 RCD falls back to 0.0 -> quantity left None"


# ---------------------------------------------------------------------------
# (2) End-to-end /document mapping per set
# ---------------------------------------------------------------------------


@pytest.fixture()
def captured_payload() -> dict:
    return {}


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, captured_payload: dict) -> TestClient:
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
                    event_id="evt-edi-golden",
                    sha256_hash="hash-1",
                    chain_hash="chain-1",
                )
            ],
        )

    monkeypatch.setattr(edi_ingestion_routes, "ingest_events", _fake_ingest_events)

    # Neutralize interchange dedup for this test app. The ISA13 dedup
    # registry lives in shared Redis keyed on the fixture's envelope IDs, so
    # whichever test file ingests a corpus fixture first claims the key and
    # this file's replays 409 depending on xdist scheduling. Dedup semantics
    # have their own suite (test_edi_dedup*); this file freezes KDE mapping.
    monkeypatch.setattr(
        edi_ingestion_routes,
        "check_and_record_interchange",
        lambda *a, **kw: (False, None),
    )

    with TestClient(app) as test_client:
        yield test_client


# Expected CTE-level mapping per set, asserted against the persisted
# IngestEvent. Values are derived from the committed fixtures.
_E2E_EXPECTED: dict[str, dict[str, Any]] = {
    "asn_856": {
        "cte_type": "shipping",
        "quantity": 200.0,
        "unit_of_measure": "cases",
        "product_description": "ROMAINE-12CT",
        "location_gln": "6141410000014",  # ship_from_gln
        "event_date": "2026-03-10",
    },
    "po_850": {
        "cte_type": "shipping",
        "quantity": 200.0,
        "unit_of_measure": "cases",
        "product_description": "ROMAINE-12CT",
        "location_gln": "6141410000014",  # seller_gln
        "event_date": "2026-03-09",  # po_date_raw
    },
    "invoice_810": {
        "cte_type": "shipping",
        "quantity": 120.0,
        "unit_of_measure": "cases",
        "product_description": "ROMAINE-12CT",
        "location_gln": "6141410000014",  # seller_gln
        "event_date": "2026-03-11",  # invoice_date_raw
    },
    "receiving_861": {
        "cte_type": "receiving",
        "quantity": 118.0,
        "unit_of_measure": "cases",
        "product_description": "ROMAINE-12CT",
        "location_gln": "6141410000069",  # receiving_location_gln
        "event_date": "2026-03-12",  # receive_date_raw
    },
}


@pytest.mark.parametrize("name", sorted(_FIXTURES))
def test_document_endpoint_maps_kdes_per_set(name: str, client: TestClient, captured_payload: dict) -> None:
    """End-to-end: POST each fixture to /document and assert the
    resulting IngestEvent CTE KDEs (quantity, product, location_gln,
    event_date/timestamp). This is the missing guard that wires extractor
    output to persisted FSMA KDEs for all four sets — not just 856.
    """
    raw = (_CORPUS_DIR / f"{name}.edi").read_bytes()
    response = client.post(
        "/api/v1/ingest/edi/document",
        data={
            "traceability_lot_code": _VALID_FSMA_TLC,
            "tenant_id": TEST_TENANT_ID,
        },
        files={"file": (f"{name}.edi", raw, "application/edi-x12")},
        headers={"X-Partner-ID": "WALMART"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["document_type"] == f"X12_{_FIXTURES[name]}"
    assert body["extracted"]["fsma_validation_status"] == "passed"

    payload = captured_payload["payload"]
    assert payload.tenant_id == TEST_TENANT_ID
    event = payload.events[0]
    exp = _E2E_EXPECTED[name]

    assert event.cte_type.value == exp["cte_type"]
    assert event.quantity == exp["quantity"]
    assert event.unit_of_measure == exp["unit_of_measure"]
    assert event.product_description == exp["product_description"]
    assert event.location_gln == exp["location_gln"]
    # event_date is preserved as the real EDI date even when the ingest
    # timestamp snaps to now() for stale-date webhook bounds (#1167).
    assert event.kdes["event_date"] == exp["event_date"]
    # Timestamp is a non-empty ISO string for every set.
    assert isinstance(event.timestamp, str) and event.timestamp
