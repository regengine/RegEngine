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
3. An explicit test pinning the quantity-fallback semantics shared by
   SN1/PO1/IT1/RCD, so a future change to any of them is a deliberate,
   reviewed decision rather than an accident. (Until #2974 the 856 SN1
   handler diverged with ``fallback=1.0``; that divergence synthesized a
   quantity the document never stated and has been removed.)

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
    _split_transaction_sets,
)
from app.webhook_compat import _batch_dedup_key  # noqa: E402
from app.webhook_models import EventResult, IngestResponse  # noqa: E402

_CORPUS_DIR = Path(__file__).parent / "fixtures" / "edi_corpus"
TEST_TENANT_ID = "00000000-0000-0000-0000-000000000123"
# TLC matching the FSMA 204 GTIN-14 + lot-suffix pattern enforced by
# shared/schemas.py:FSMAEvent.validate_tlc_format (strict mode passes).
_VALID_FSMA_TLC = "00012345678901-LOT001"

# Map fixture stem -> expected transaction set, for the end-to-end loop.
# One ST/SE pair each; ``_MULTI_SET_FIXTURES`` below covers batched
# interchanges, which snapshot a list rather than a single dict.
_FIXTURES = {
    "asn_856": "856",
    # #2974: three item-level SN1 lines in one ASN, in cartons (CT).
    "asn_856_multi_line": "856",
    "po_850": "850",
    "invoice_810": "810",
    "receiving_861": "861",
    "receipt_944": "944",
    "advice_945": "945",
}

# #2976: fixture stem -> the transaction set every ST/SE pair carries.
_MULTI_SET_FIXTURES = {
    "asn_856_batch": "856",
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


@pytest.mark.parametrize("name", sorted(_MULTI_SET_FIXTURES))
def test_edi_multi_set_extractor_golden(name: str) -> None:
    """#2976: a batched interchange snapshots one extraction PER ST/SE
    pair, and no slice may read a body segment from another set.

    Before #2976 the corpus had no multi-ST fixture at all, so the
    silent collapse of a batched file into one merged event had no test
    that could fail.
    """
    raw = (_CORPUS_DIR / f"{name}.edi").read_text(encoding="utf-8")
    segments = _parse_x12_segments(raw)
    set_slices = _split_transaction_sets(segments)
    assert len(set_slices) > 1, f"{name}.edi must carry more than one ST/SE pair"

    actual = []
    for slice_segments in set_slices:
        transaction_set = _detect_transaction_set(slice_segments)
        assert transaction_set == _MULTI_SET_FIXTURES[name]
        actual.append(_extract_fields_for_set(transaction_set, slice_segments))

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
        f"EDI extraction for {name!r} drifted from the committed golden snapshot.\n"
        f"expected={json.dumps(expected, indent=2, sort_keys=True)}\n"
        f"actual={json.dumps(actual, indent=2, sort_keys=True)}"
    )

    # Every set must be distinguishable — a merged extraction would
    # collapse these into one repeated value.
    asn_numbers = [item["asn_number"] for item in actual]
    assert len(set(asn_numbers)) == len(asn_numbers), "#2976: ASN numbers bled across ST/SE boundaries"
    ship_from = [item["ship_from_name"] for item in actual]
    assert len(set(ship_from)) == len(ship_from), "#2976: N1 ship-from bled across ST/SE boundaries"


def test_856_lot_is_read_from_lin_ref_or_sln() -> None:
    """A line lot may sit on LIN, on REF*LT after SN1, or on an SLN LT pair.
    """
    isa = "ISA*00*          *00*          *ZZ*SENDERID       *ZZ*RECEIVERID     *260310*1200*U*00401*000000009*0*P*>~"
    raw = (
        isa
        + "GS*SH*S*R*20260310*1200*1*X*004010~ST*856*0001~BSN*00*A*20260310*1200~"
        + "LIN**LT*LOT-A*SK*ROM~SN1**10*CA~"
        + "LIN**SK*SPI~SN1**20*CA~REF*LT*LOT-B~"
        + "LIN**SK*KALE~SN1**30*CA~SLN*1**I*30*CA****LT*LOT-C~"
        + "SE*8*0001~GE*1*1~IEA*1*000000009~"
    )
    lines = _extract_fields_for_set("856", _parse_x12_segments(raw))["line_items"]
    assert [(line["lot_number"], line["quantity"], line["product_description"]) for line in lines] == [
        ("LOT-A", 10.0, "ROM"),
        ("LOT-B", 20.0, "SPI"),
        ("LOT-C", 30.0, "KALE"),
    ]


def test_856_multi_sn1_keeps_each_line() -> None:
    """Each SN1 is its own line. 120 + 80 + 40 must not collapse to 240.
    """
    raw = (_CORPUS_DIR / "asn_856_multi_line.edi").read_text(encoding="utf-8")
    extracted = _extract_fields_for_set("856", _parse_x12_segments(raw))
    assert [(line["quantity"], line["unit_of_measure"]) for line in extracted["line_items"]] == [
        (120.0, "CT"),
        (80.0, "CT"),
        (40.0, "CT"),
    ]


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
    RCD is ``RCD*1*118*CT**4`` -> condition_code ``4`` at index 5.
    """
    raw = (_CORPUS_DIR / "receiving_861.edi").read_text(encoding="utf-8")
    extracted = _extract_fields_for_set("861", _parse_x12_segments(raw))
    assert extracted["line_items"][0]["condition_code"] == "4"


def test_861_bra_element_offsets_match_x12_layout() -> None:
    """#2973: BRA01 is the receiving advice number and BRA02 the date.

    BRA is the outlier among X12 beginning segments — the Transaction Set
    Purpose Code sits at BRA03, not first as in BSN01/BEG01 — so reading
    ``bra[2]``/``bra[3]`` (the 856 BSN offsets) filed the date as the
    advice number and the two-character purpose code as the date, which
    ``_parse_edi_date_digits`` rejects with a 400.
    """
    isa = "ISA*00*          *00*          *ZZ*SENDERID       *ZZ*RECEIVERID     *260310*1200*U*00401*000000011*0*P*>~"
    raw = (
        isa
        + "GS*RC*SENDERID*RECEIVERID*20260310*1200*1*X*004010~ST*861*0001~"
        + "BRA*RA-9090*20260312*00*1~SE*3*0001~GE*1*1~IEA*1*000000011~"
    )

    extracted = _extract_fields_for_set("861", _parse_x12_segments(raw))

    assert extracted["receiving_advice_number"] == "RA-9090"
    assert extracted["receive_date_raw"] == "20260312"
    assert extracted["reference_document_number"] == "RA-9090"


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
    """#2536 acceptance, updated by #2974: pin the quantity-fallback
    semantics shared by every transaction set.

    When a quantity element is PRESENT but non-numeric, all four
    handlers use ``_safe_float(..., fallback=0.0)``, so the running
    total stays 0 and ``quantity`` is left None.

    This test previously pinned the opposite for 856 — ``fallback=1.0``,
    justified as "a shipment notice implies at least one unit shipped".
    #2974 removed that divergence: the value is not in the document, so
    inventing 1.0 fabricates an FSMA 204 quantity KDE, which is the
    exact failure class ``_legacy_856_placeholder_errors`` was added to
    stop. The route now fails closed instead (see
    ``routes._build_ingest_event_for_set``), so a real quantity is still
    required — it just is not synthesized.
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
        + "BRA*RA-1*20260312*00*1~RCD*1*ABC*CA~SE*5*0001~GE*1*1~IEA*1*000000009~"
    )

    q856 = _extract_fields_for_set("856", _parse_x12_segments(e856))["line_items"][0]["quantity"]
    q850 = _extract_fields_for_set("850", _parse_x12_segments(e850))["quantity"]
    q810 = _extract_fields_for_set("810", _parse_x12_segments(e810))["quantity"]
    q861 = _extract_fields_for_set("861", _parse_x12_segments(e861))["line_items"][0]["quantity"]

    assert q856 is None, "#2974: 856 SN1 falls back to 0.0 -> quantity left None"
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
        return IngestResponse(
            accepted=len(payload.events),
            rejected=0,
            total=len(payload.events),
            events=[
                EventResult(
                    traceability_lot_code=event.traceability_lot_code,
                    cte_type=event.cte_type.value,
                    status="accepted",
                    event_id=f"evt-edi-golden-{index}",
                    sha256_hash="hash-1",
                    chain_hash="chain-1",
                )
                for index, event in enumerate(payload.events, start=1)
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
        "unit_of_measure": "cases",  # SN1 "CA"
        "product_description": "ROMAINE-12CT",
        "location_gln": "6141410000014",  # ship_from_gln
        "event_date": "2026-03-10",
    },
    "asn_856_multi_line": {
        "cte_type": "shipping",
        "quantity": 120.0,  # first SN1; 80 and 40 are their own events
        "unit_of_measure": "cartons",  # #2978: SN1 "CT"
        "product_description": "ROMAINE-12CT",
        "location_gln": "6141410000014",  # ship_from_gln
        "event_date": "2026-03-10",
    },
    "po_850": {
        "cte_type": "shipping",
        "quantity": 200.0,
        "unit_of_measure": "boxes",  # #2978: PO1 "BX"
        "product_description": "ROMAINE-12CT",
        "location_gln": "6141410000014",  # seller_gln
        "event_date": "2026-03-09",  # po_date_raw
    },
    "invoice_810": {
        "cte_type": "shipping",
        "quantity": 120.0,
        "unit_of_measure": "cases",  # #2978: IT1 "CS"
        "product_description": "ROMAINE-12CT",
        "location_gln": "6141410000014",  # seller_gln
        "event_date": "2026-03-11",  # invoice_date_raw
    },
    "receiving_861": {
        "cte_type": "receiving",
        "quantity": 118.0,
        "unit_of_measure": "cartons",  # #2978: RCD "CT"
        "product_description": "ROMAINE-12CT",
        "location_gln": "6141410000069",  # receiving_location_gln
        "event_date": "2026-03-12",  # receive_date_raw
    },
    "receipt_944": {
        "cte_type": "receiving",
        "quantity": 10.0,
        "unit_of_measure": "cases",  # W07 "CA"
        "product_description": "Romaine Hearts 12ct",
        "location_gln": "6141410000069",  # warehouse GLN
        "event_date": "2026-03-18",  # W17 date, not G62
    },
    "advice_945": {
        "cte_type": "shipping",
        "quantity": 10.0,  # W1203 shipped, not W1202 ordered
        "unit_of_measure": "cases",
        "product_description": "Romaine Hearts 12ct",
        "location_gln": "6141410000069",  # ship-from warehouse GLN
        "event_date": "2026-03-19",  # W06 date, not G62
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
    data = {
        "traceability_lot_code": _VALID_FSMA_TLC,
        "tenant_id": TEST_TENANT_ID,
    }
    if name in ("receipt_944", "advice_945"):
        data["tlc_source_reference"] = "Packinghouse Assigner"
    response = client.post(
        "/api/v1/ingest/edi/document",
        data=data,
        files={"file": (f"{name}.edi", raw, "application/edi-x12")},
        headers={"X-Partner-ID": "WALMART"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["document_type"] == f"X12_{_FIXTURES[name]}"
    assert body["extracted"]["fsma_validation_status"] == "passed"
    if name in ("receipt_944", "advice_945"):
        assert body["extracted"]["event_count"] == 3
        assert body["ingestion_result"]["total"] == len(body["ingestion_result"]["events"]) == 3
        assert [event.traceability_lot_code for event in captured_payload["payload"].events] == [
            "00012345678905-A",
            "00012345678912-B",
            "00012345678929-C",
        ]
        assert [event.quantity for event in captured_payload["payload"].events] == [10.0, 20.0, 30.0]
        assert [event.unit_of_measure for event in captured_payload["payload"].events] == ["cases", "cases", "each"]
    if name == "asn_856_multi_line":
        posted = captured_payload["payload"].events
        assert [event.quantity for event in posted] == [120.0, 80.0, 40.0]
        assert {event.traceability_lot_code for event in posted} == {_VALID_FSMA_TLC}
        assert len({_batch_dedup_key(event) for event in posted}) == 3

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


def test_861_bsn_ordered_bra_is_rejected(client: TestClient) -> None:
    """#2973: an 861 carrying the old purpose-code-first (BSN-style) BRA
    must be rejected with ``invalid_edi_date`` rather than silently
    filing the purpose code as the receive date.
    """
    conformant = (_CORPUS_DIR / "receiving_861.edi").read_text(encoding="utf-8")
    legacy = conformant.replace("BRA*RA-9090*20260312*00*1~", "BRA*00*RA-9090*20260312~")
    assert legacy != conformant, "corpus fixture must use the conformant BRA element order"

    response = client.post(
        "/api/v1/ingest/edi/document",
        data={
            "traceability_lot_code": _VALID_FSMA_TLC,
            "tenant_id": TEST_TENANT_ID,
        },
        files={"file": ("receiving_861_legacy.edi", legacy.encode("utf-8"), "application/edi-x12")},
        headers={"X-Partner-ID": "WALMART"},
    )

    assert response.status_code == 400, response.text
    assert response.json()["detail"]["error"] == "invalid_edi_date"


def _three_line_document(transaction_set: str, lots: tuple[str, str, str], units: tuple[str, str, str]) -> bytes:
    """One interchange whose three item lines carry lots and their own units."""
    isa = "ISA*00*          *00*          *ZZ*SENDERID       *ZZ*RECEIVERID     *260310*1200*U*00401*000000321*0*P*>~"
    if transaction_set == "856":
        body = (
            "GS*SH*SENDERID*RECEIVERID*20260310*1200*1*X*004010~"
            "ST*856*0001~BSN*00*ASN-ABC*20260310*1200~HL*1**S~"
            "N1*SF*Valley Fresh Farms*92*6141410000014~"
            "N1*ST*Metro Distribution Center*92*6141410000069~"
            f"LIN**SK*ROMAINE-12CT*LT*{lots[0]}~SN1**10*CA~"
            f"LIN**SK*SPINACH-6CT*LT*{lots[1]}~SN1**20*LB~"
            f"LIN**UP*012345678905*LT*{lots[2]}~SN1**30*EA~"
            "REF*BM*BOL-ABC~SE*12*0001~GE*1*1~IEA*1*000000321~"
        )
    else:
        body = (
            "GS*RC*SENDERID*RECEIVERID*20260310*1200*1*X*004010~"
            "ST*861*0001~BRA*RA-ABC*20260312*00*1~"
            "N1*SF*Valley Fresh Farms*92*6141410000014~"
            "N1*ST*Metro Distribution Center*92*6141410000069~"
            f"RCD*1*10*{units[0]}**4~LIN**SK*ROMAINE-12CT*LT*{lots[0]}~"
            f"RCD*2*20*{units[1]}**5~LIN**SK*SPINACH-6CT*LT*{lots[1]}~"
            f"RCD*3*30*{units[2]}**6~LIN**UP*012345678905*LT*{lots[2]}~"
            "REF*PO*PO-ABC~SE*12*0001~GE*1*1~IEA*1*000000321~"
        )
    return (isa + body).encode("utf-8")


@pytest.mark.parametrize("transaction_set", ["856", "861"])
def test_three_item_lines_become_three_events(transaction_set: str, client: TestClient, captured_payload: dict) -> None:
    """Lots A, B and C are three CTEs. The TLC is the lot verbatim, and
    two lines that share a lot still both survive batch dedup.
    """
    lots = ("00012345678901-A", "00012345678901-B", "00012345678901-C")
    units = ("CA", "LB", "EA") if transaction_set == "856" else ("CA", "LB", "EA")
    raw = _three_line_document(transaction_set, lots, units)
    response = client.post(
        "/api/v1/ingest/edi/document",
        data={"traceability_lot_code": _VALID_FSMA_TLC, "tenant_id": TEST_TENANT_ID},
        files={"file": (f"{transaction_set}.edi", raw, "application/edi-x12")},
        headers={"X-Partner-ID": "WALMART"},
    )
    assert response.status_code == 201, response.text
    events = captured_payload["payload"].events
    assert [(event.traceability_lot_code, event.quantity, event.unit_of_measure) for event in events] == [
        ("00012345678901-A", 10.0, "cases"),
        ("00012345678901-B", 20.0, "lbs"),
        ("00012345678901-C", 30.0, "each"),
    ]
    assert events[2].traceability_lot_code == "00012345678901-C"
    assert "012345678905" not in events[2].traceability_lot_code
    assert len({_batch_dedup_key(event) for event in events}) == 3
    assert len({event.kdes["edi_line_index"] for event in events}) == 3
    if transaction_set == "856":
        assert {event.kdes["asn_number"] for event in events} == {"ASN-ABC"}
        assert {event.kdes["ship_from_location"] for event in events} == {"Valley Fresh Farms"}
    else:
        assert {event.kdes["receiving_advice_number"] for event in events} == {"RA-ABC"}
        assert [event.kdes["condition_code"] for event in events] == ["4", "5", "6"]

    shared = _three_line_document(transaction_set, (lots[0], lots[0], lots[0]), units)
    captured_payload.clear()
    again = client.post(
        "/api/v1/ingest/edi/document",
        data={"traceability_lot_code": _VALID_FSMA_TLC, "tenant_id": TEST_TENANT_ID},
        files={"file": (f"{transaction_set}-same-lot.edi", shared, "application/edi-x12")},
        headers={"X-Partner-ID": "WALMART"},
    )
    assert again.status_code == 201, again.text
    same_lot = captured_payload["payload"].events
    assert [event.traceability_lot_code for event in same_lot] == [lots[0], lots[0], lots[0]]
    assert [event.quantity for event in same_lot] == [10.0, 20.0, 30.0]
    assert len({_batch_dedup_key(event) for event in same_lot}) == 3


def test_line_without_a_lot_uses_the_form_field_and_a_short_lot_is_not_prefixed(
    client: TestClient, captured_payload: dict
) -> None:
    """The form TLC is only the fallback. A lot of ``A`` is rejected as
    itself; it is not rewritten to a GTIN-prefixed TLC.
    """
    isa = "ISA*00*          *00*          *ZZ*SENDERID       *ZZ*RECEIVERID     *260310*1200*U*00401*000000322*0*P*>~"
    no_lot = (
        isa
        + "GS*SH*SENDERID*RECEIVERID*20260310*1200*1*X*004010~ST*856*0001~"
        + "BSN*00*ASN-1*20260310*1200~HL*1**S~"
        + "N1*SF*Valley Fresh Farms*92*6141410000014~"
        + "N1*ST*Metro Distribution Center*92*6141410000069~"
        + "LIN**SK*ROMAINE-12CT~SN1**10*CA~REF*BM*BOL-1~SE*9*0001~GE*1*1~IEA*1*000000322~"
    )
    response = client.post(
        "/api/v1/ingest/edi/document",
        data={"traceability_lot_code": _VALID_FSMA_TLC, "tenant_id": TEST_TENANT_ID},
        files={"file": ("no-lot.edi", no_lot.encode("utf-8"), "application/edi-x12")},
        headers={"X-Partner-ID": "WALMART"},
    )
    assert response.status_code == 201, response.text
    assert captured_payload["payload"].events[0].traceability_lot_code == _VALID_FSMA_TLC

    short = no_lot.replace("LIN**SK*ROMAINE-12CT~", "LIN**UP*012345678905*LT*A~")
    captured_payload.clear()
    rejected = client.post(
        "/api/v1/ingest/edi/document",
        data={"traceability_lot_code": _VALID_FSMA_TLC, "tenant_id": TEST_TENANT_ID},
        files={"file": ("short-lot.edi", short.encode("utf-8"), "application/edi-x12")},
        headers={"X-Partner-ID": "WALMART"},
    )
    assert rejected.status_code == 422, rejected.text
    detail = rejected.json()["detail"]
    assert detail["error"] == "fsma_validation_failed"
    assert "012345678905" not in json.dumps(detail)
    assert "payload" not in captured_payload
