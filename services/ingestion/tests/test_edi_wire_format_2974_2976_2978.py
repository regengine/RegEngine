"""X12 wire-format regression tests for #2976, #2978 and #2974.

These three defects all live on the unified EDI route
(``POST /api/v1/ingest/edi/document``) and all corrupt the FSMA 204
traceability record silently — the request still returns HTTP 201.

#2976  An interchange carrying several ST/SE transaction sets is never
       decomposed. Every extractor walks the whole flat segment list, so
       transaction sets 2..N are dropped and their N1/SN1/REF segments
       bleed into the single surviving event.

#2978  ``_X12_UOM_MAP`` is keyed on values that cannot be X12 data
       element 355 codes (DE355 is ID 2/2 — exactly two characters), so
       the real two-character codes miss the lookup and degrade to
       ``"units"`` with no log and no rejection.

#2974  The 856 extractor assigns ``data["quantity"]`` on every SN1
       instead of accumulating, so a multi-line ASN reports only its
       final line's quantity while 850/810/861 all sum.
"""

from __future__ import annotations

import logging
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
from app.edi_ingestion import router as edi_router  # noqa: E402
from app.edi_ingestion.extractors import _extract_fields_for_set  # noqa: E402
from app.edi_ingestion.parser import _parse_x12_segments  # noqa: E402
from app.edi_ingestion.utils import _normalize_unit  # noqa: E402
from app.webhook_models import EventResult, IngestResponse  # noqa: E402

TEST_TENANT_ID = "00000000-0000-0000-0000-000000000123"
# TLC matching the FSMA 204 GTIN-14 + lot-suffix pattern enforced by
# shared/schemas.py:FSMAEvent.validate_tlc_format (strict mode passes).
_VALID_FSMA_TLC = "00012345678901-LOT001"

# 106-char ISA header (index 105 is the segment terminator the parser
# sniffs). Shared by every envelope below; only ISA13 varies.
_ISA_TEMPLATE = (
    "ISA*00*          *00*          *ZZ*SENDERID       *ZZ*RECEIVERID     "
    "*260310*1200*U*00401*{isa13}*0*P*>~"
)
_GS_856 = "GS*SH*SENDERID*RECEIVERID*20260310*1200*1*X*004010~"

# Check-digit-valid GLNs, same pair the committed corpus uses.
_SHIP_FROM_GLN = "6141410000014"
_SHIP_TO_GLN = "6141410000069"


def _isa(isa13: str) -> str:
    header = _ISA_TEMPLATE.format(isa13=isa13)
    assert len(header) == 106, f"ISA header must be 106 chars (got {len(header)})"
    return header


def _856_set(
    *,
    control: str,
    asn: str,
    ship_from: str,
    bol: str,
    sn1_lines: tuple[tuple[str, str], ...] = (("200", "CA"),),
) -> str:
    """One conformant 856 ST/SE transaction set.

    ``SE01`` is computed from the real segment count (ST..SE inclusive)
    so the envelope this helper emits is valid X12 rather than merely
    parseable.
    """
    body = [
        f"ST*856*{control}~",
        f"BSN*00*{asn}*20260310*1200~",
        "HL*1**S~",
        f"N1*SF*{ship_from}*92*{_SHIP_FROM_GLN}~",
        f"N1*ST*Metro Distribution Center*92*{_SHIP_TO_GLN}~",
        "LIN**SK*ROMAINE-12CT~",
    ]
    body += [f"SN1**{qty}*{uom}~" for qty, uom in sn1_lines]
    body.append(f"REF*BM*{bol}~")
    body.append(f"SE*{len(body) + 1}*{control}~")
    return "".join(body)


def _interchange_856_two_sn1_units(uom_a: str, uom_b: str) -> bytes:
    """A single conformant 856 whose two SN1 lines carry the given units.

    Used by the PR #2991 review-finding tests: 120 + 80 = 200 whenever the
    two codes resolve to the same FSMA unit.
    """
    return _interchange(
        [
            _856_set(
                control="0001",
                asn="ASN-UOM",
                ship_from="Valley Fresh Farms",
                bol="BOL-UOM",
                sn1_lines=(("120", uom_a), ("80", uom_b)),
            )
        ],
        isa13="000029911",
    )


def _interchange(sets: list[str], *, isa13: str, ge01: str | None = None) -> bytes:
    """Wrap transaction sets in one ISA/GS ... GE/IEA interchange.

    GE01 defaults to the true ST count so the envelope is conformant;
    pass ``ge01`` explicitly to build the mismatched-count case.
    """
    ge = ge01 if ge01 is not None else str(len(sets))
    raw = _isa(isa13) + _GS_856 + "".join(sets) + f"GE*{ge}*1~" + f"IEA*1*{isa13}~"
    return raw.encode("utf-8")


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
                    event_id=f"evt-edi-{idx}",
                    sha256_hash="hash-1",
                    chain_hash="chain-1",
                )
                for idx, event in enumerate(payload.events)
            ],
        )

    monkeypatch.setattr(edi_ingestion_routes, "ingest_events", _fake_ingest_events)

    # Neutralize ISA13 interchange dedup — it lives in shared Redis keyed
    # on envelope IDs, so cross-file test ordering would otherwise 409
    # these replays. Dedup has its own suite (test_edi_dedup*).
    monkeypatch.setattr(
        edi_ingestion_routes,
        "check_and_record_interchange",
        lambda *a, **kw: (False, None),
    )

    with TestClient(app) as test_client:
        yield test_client


def _post(
    client: TestClient,
    raw: bytes,
    name: str = "batch.edi",
    extra_data: dict[str, str] | None = None,
):
    return client.post(
        "/api/v1/ingest/edi/document",
        data={
            "traceability_lot_code": _VALID_FSMA_TLC,
            "tenant_id": TEST_TENANT_ID,
            **(extra_data or {}),
        },
        files={"file": (name, raw, "application/edi-x12")},
        headers={"X-Partner-ID": "WALMART"},
    )


# ---------------------------------------------------------------------------
# #2976 — multiple ST/SE transaction sets
# ---------------------------------------------------------------------------


def test_2976_multi_st_interchange_emits_one_event_per_transaction_set(
    client: TestClient, captured_payload: dict
) -> None:
    """A batched interchange must produce one CTE per ST/SE pair with no
    cross-shipment field bleed.

    Batching a nightly run of ASNs into one ISA/GS with N ST/SE pairs is
    standard X12. Before #2976 this returned 201 with exactly ONE event
    that carried the FIRST set's BSN/REF, an arbitrary set's N1 partner,
    and the LAST set's SN1 quantity — a chimera that can attribute one
    supplier's lot to another supplier's location in a recall trace.
    """
    raw = _interchange(
        [
            _856_set(
                control="0001",
                asn="ASN-AAA",
                ship_from="Valley Fresh Farms",
                bol="BOL-AAA",
                sn1_lines=(("120", "CA"),),
            ),
            _856_set(
                control="0002",
                asn="ASN-BBB",
                ship_from="Coastal Greens",
                bol="BOL-BBB",
                sn1_lines=(("240", "CA"),),
            ),
            _856_set(
                control="0003",
                asn="ASN-CCC",
                ship_from="Highland Produce",
                bol="BOL-CCC",
                sn1_lines=(("360", "CA"),),
            ),
        ],
        isa13="000029761",
    )

    response = _post(client, raw)
    assert response.status_code == 201, response.text

    payload = captured_payload["payload"]
    assert len(payload.events) == 3, (
        f"#2976: a 3-transaction-set interchange must emit 3 CTE events, got {len(payload.events)} — "
        "the other transaction sets were silently dropped."
    )

    by_asn = {event.kdes.get("asn_number"): event for event in payload.events}
    assert set(by_asn) == {"ASN-AAA", "ASN-BBB", "ASN-CCC"}

    expected = {
        "ASN-AAA": ("Valley Fresh Farms", "BOL-AAA", 120.0, "0001"),
        "ASN-BBB": ("Coastal Greens", "BOL-BBB", 240.0, "0002"),
        "ASN-CCC": ("Highland Produce", "BOL-CCC", 360.0, "0003"),
    }
    for asn, (ship_from, bol, quantity, control) in expected.items():
        event = by_asn[asn]
        assert event.kdes["ship_from_location"] == ship_from, f"#2976: {asn} ship-from bled across ST/SE boundary"
        assert event.kdes["reference_document_number"] == bol, f"#2976: {asn} REF bled across ST/SE boundary"
        assert event.quantity == quantity, f"#2976: {asn} SN1 quantity bled across ST/SE boundary"
        assert event.kdes["edi_control_number"] == control

    body = response.json()
    assert body["extracted"]["transaction_set_count"] == 3


def test_2976_ge01_disagreeing_with_st_count_is_rejected(client: TestClient, captured_payload: dict) -> None:
    """GE01 (number of transaction sets in the functional group) must be
    checked against the real ST count.

    A truncated or mis-assembled batch — GE01 says 3, only 2 ST/SE pairs
    arrived — has to fail closed, not silently ingest the sets that made
    it through.
    """
    raw = _interchange(
        [
            _856_set(control="0001", asn="ASN-AAA", ship_from="Valley Fresh Farms", bol="BOL-AAA"),
            _856_set(control="0002", asn="ASN-BBB", ship_from="Coastal Greens", bol="BOL-BBB"),
        ],
        isa13="000029762",
        ge01="3",
    )

    response = _post(client, raw)
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "transaction_set_count_mismatch"
    assert detail["declared"] == 3
    assert detail["actual"] == 2
    assert "payload" not in captured_payload, "nothing may reach the canonical stream on a count mismatch"


# ---------------------------------------------------------------------------
# #2978 — X12 data element 355 unit codes
# ---------------------------------------------------------------------------


def test_2978_real_element_355_codes_map_instead_of_degrading_to_units() -> None:
    """The real two-character DE355 codes must resolve to the FSMA
    vocabulary instead of silently becoming ``"units"``.

    X12 data element 355 (Unit or Basis for Measurement Code) is ID 2/2,
    so a three-character key like ``CTN`` cannot be a DE355 value at all
    while its real code ``CT`` was missing from the table entirely.
    ``VALID_UNITS_OF_MEASURE`` already contains every target below, so
    this is purely a wrong-key lookup.
    """
    assert _normalize_unit("CT") == "cartons"
    assert _normalize_unit("BX") == "boxes"
    assert _normalize_unit("CS") == "cases"
    assert _normalize_unit("BG") == "bags"

    # Codes that already worked must keep working.
    assert _normalize_unit("CA") == "cases"
    assert _normalize_unit("LB") == "lbs"
    assert _normalize_unit("KG") == "kg"
    assert _normalize_unit("EA") == "each"
    assert _normalize_unit("PC") == "pieces"


def test_2978_unmapped_unit_warns_and_fails_closed_on_document_route(
    client: TestClient, captured_payload: dict, caplog: pytest.LogCaptureFixture
) -> None:
    """A present-but-unrecognised UOM code must be visible and must fail
    closed on ``/edi/document``.

    Silently rewriting an unknown code to ``"units"`` produces a quantity
    KDE that is numerically right and semantically meaningless, with
    nothing in the logs or the response to show it happened.
    """
    ok = _interchange(
        [
            _856_set(
                control="0001",
                asn="ASN-CT",
                ship_from="Valley Fresh Farms",
                bol="BOL-CT",
                sn1_lines=(("200", "CT"),),
            )
        ],
        isa13="000029781",
    )
    response = _post(client, ok, name="cartons.edi")
    assert response.status_code == 201, response.text
    assert captured_payload["payload"].events[0].unit_of_measure == "cartons"

    captured_payload.clear()
    with caplog.at_level(logging.WARNING, logger="edi-ingestion"):
        assert _normalize_unit("ZQ") == "units"
    assert any("ZQ" in record.getMessage() for record in caplog.records), (
        "#2978: an unmapped X12 UOM code must emit a WARNING containing the raw code"
    )

    bad = _interchange(
        [
            _856_set(
                control="0001",
                asn="ASN-ZQ",
                ship_from="Valley Fresh Farms",
                bol="BOL-ZQ",
                sn1_lines=(("200", "ZQ"),),
            )
        ],
        isa13="000029782",
    )
    response = _post(client, bad, name="bad-uom.edi")
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["error"] == "edi_unmapped_unit_of_measure"
    assert "payload" not in captured_payload, "an unmapped unit must not reach the canonical stream"


# ---------------------------------------------------------------------------
# #2974 — repeated SN1 segments in one 856
# ---------------------------------------------------------------------------


def test_2974_multi_sn1_856_quantity_is_summed_not_last_wins(
    client: TestClient, captured_payload: dict
) -> None:
    """Repeated SN1 lines in one 856 must accumulate the way PO1/IT1/RCD
    already do, rather than the last line overwriting all the others.

    The 850 corpus fixture already asserts the summed 200.0 across two
    PO1 lines; the 856 handler was the sole outlier, so a 12-line pallet
    shipment persisted only its final line's quantity.
    """
    raw_856 = _interchange(
        [
            _856_set(
                control="0001",
                asn="ASN-MULTI",
                ship_from="Valley Fresh Farms",
                bol="BOL-MULTI",
                sn1_lines=(("120", "CA"), ("80", "CA")),
            )
        ],
        isa13="000029741",
    )

    extracted = _extract_fields_for_set("856", _parse_x12_segments(raw_856.decode("utf-8")))
    assert extracted["quantity"] == 200.0, (
        f"#2974: two SN1 lines of 120 + 80 must extract 200.0, got {extracted['quantity']} "
        "(last-segment-wins discards every line but the last)"
    )
    assert extracted["unit_of_measure"] == "CA"

    response = _post(client, raw_856, name="multi-sn1.edi")
    assert response.status_code == 201, response.text
    assert captured_payload["payload"].events[0].quantity == 200.0

    # A zero line can no longer synthesize the 1.0 SN1 fallback.
    raw_zero = _interchange(
        [
            _856_set(
                control="0001",
                asn="ASN-ZERO",
                ship_from="Valley Fresh Farms",
                bol="BOL-ZERO",
                sn1_lines=(("0", "CA"),),
            )
        ],
        isa13="000029742",
    )
    zero_extracted = _extract_fields_for_set("856", _parse_x12_segments(raw_zero.decode("utf-8")))
    assert zero_extracted["quantity"] is None, "#2974: SN1**0*CA must not fabricate a quantity of 1.0"


def test_2974_sn1_lines_disagreeing_on_unit_are_rejected(client: TestClient, captured_payload: dict) -> None:
    """Summing SN1 lines that carry different UOM codes would pair a
    total with an arbitrary unit, so the document must be rejected.

    120 cases + 80 pounds is not 200 of anything.
    """
    raw = _interchange(
        [
            _856_set(
                control="0001",
                asn="ASN-MIXED",
                ship_from="Valley Fresh Farms",
                bol="BOL-MIXED",
                sn1_lines=(("120", "CA"), ("80", "LB")),
            )
        ],
        isa13="000029743",
    )

    response = _post(client, raw, name="mixed-uom.edi")
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "edi_856_mixed_units_of_measure"
    assert sorted(detail["units"]) == ["CA", "LB"]
    assert "payload" not in captured_payload


def test_2976_legacy_856_endpoint_refuses_a_batched_interchange(
    client: TestClient, captured_payload: dict
) -> None:
    """The legacy single-ASN endpoint extracts from the flat segment list,
    so a batched interchange would merge every ST/SE pair into its one
    event. It must refuse and point the caller at ``/document``.
    """
    raw = _interchange(
        [
            _856_set(control="0001", asn="ASN-AAA", ship_from="Valley Fresh Farms", bol="BOL-AAA"),
            _856_set(control="0002", asn="ASN-BBB", ship_from="Coastal Greens", bol="BOL-BBB"),
        ],
        isa13="000029763",
    )

    response = client.post(
        "/api/v1/ingest/edi",
        data={
            "traceability_lot_code": "LOT-2026-EDI-BATCH",
            "tenant_id": TEST_TENANT_ID,
        },
        files={"file": ("batch.edi", raw, "application/edi-x12")},
        headers={"X-Partner-ID": "WALMART"},
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "multiple_transaction_sets"
    assert detail["transaction_set_count"] == 2
    assert "payload" not in captured_payload


def test_2976_batched_interchange_never_half_lands(client: TestClient, captured_payload: dict) -> None:
    """A batch is all-or-nothing across the canonical stream.

    In advisory mode (``?strict=false``) a batch whose sets fail FSMA
    validation records a rejection per failing set and calls
    ``ingest_events`` for none of them — the #1174 invariant that an EDI
    document lives in the canonical stream OR the rejection log, never
    both, has to hold per interchange and not just per event.
    """
    from app.edi_ingestion.rejection_log import list_edi_rejections, reset_edi_rejections

    reset_edi_rejections()
    captured_payload.clear()

    raw = _interchange(
        [
            _856_set(control="0001", asn="ASN-AAA", ship_from="Valley Fresh Farms", bol="BOL-AAA"),
            _856_set(control="0002", asn="ASN-BBB", ship_from="Coastal Greens", bol="BOL-BBB"),
        ],
        isa13="000029764",
    )

    response = client.post(
        "/api/v1/ingest/edi/document",
        params={"strict": "false"},
        data={
            # Fails FSMAEvent.validate_tlc_format for every set.
            "traceability_lot_code": "not-a-gtin-tlc",
            "tenant_id": TEST_TENANT_ID,
        },
        files={"file": ("batch.edi", raw, "application/edi-x12")},
        headers={"X-Partner-ID": "WALMART"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "rejected"
    assert body["ingestion_result"] is None
    assert body["extracted"]["transaction_set_count"] == 2
    assert [item["fsma_validation_status"] for item in body["extracted"]["transaction_sets"]] == ["failed", "failed"]
    assert "payload" not in captured_payload, "no transaction set of a failing batch may reach the canonical stream"

    # One audit record per failing transaction set, not one per file.
    assert len(list_edi_rejections(TEST_TENANT_ID)) == 2


def test_856_batch_missing_kde_identifies_failing_transaction_set(
    client: TestClient,
    captured_payload: dict,
) -> None:
    """A batch rejection must identify the incomplete transaction set."""
    incomplete_set = (
        _856_set(
            control="0002",
            asn="ASN-BBB",
            ship_from="Coastal Greens",
            bol="BOL-BBB",
        )
        .replace("LIN**SK*ROMAINE-12CT~", "")
        .replace("SE*9*0002~", "SE*8*0002~")
    )
    raw = _interchange(
        [
            _856_set(
                control="0001",
                asn="ASN-AAA",
                ship_from="Valley Fresh Farms",
                bol="BOL-AAA",
            ),
            incomplete_set,
        ],
        isa13="000029914",
    )

    response = _post(client, raw, name="batch-missing-product.edi")

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "edi_856_missing_required_kdes"
    assert detail["transaction_set_index"] == 1
    assert detail["transaction_set"] == "856"
    assert detail["control_number"] == "0002"
    assert "product_description" in detail["missing_kdes"]
    assert "payload" not in captured_payload


# ── Review findings on PR #2991 ───────────────────────────────────────────
# Both are consequences of features this PR introduced, caught in review.


def test_sn1_equivalent_unit_codes_are_not_falsely_rejected():
    """CA and CS both resolve to "cases" (constants.py:20-21), so an 856
    whose SN1 lines use both genuinely agrees on the unit and must sum.

    The guard originally compared raw element-355 codes, which made this a
    422. This PR is what added CS to the map, so raw comparison would have
    created the false rejection it is now guarded against.
    """
    from app.edi_ingestion.extractors import _extract_856_fields
    from app.edi_ingestion.parser import _parse_x12_segments
    from app.edi_ingestion.utils import _resolve_unit_code

    segments = _parse_x12_segments(_interchange_856_two_sn1_units("CA", "CS").decode())
    data = _extract_856_fields(segments)

    assert data["quantity"] == 200.0, "equivalent unit codes must still sum"
    # The extractor keeps the raw element-355 code; normalization to the
    # FSMA vocabulary happens downstream. What matters here is that both
    # codes resolve to the same unit, which is why the sum is legitimate.
    assert data["unit_of_measure"] == "CA"
    assert _resolve_unit_code("CA") == _resolve_unit_code("CS") == "cases"


def test_sn1_genuinely_different_units_are_still_rejected():
    """The relaxation must not weaken the real guard: cases vs pounds is
    still not 200 of anything."""
    from fastapi import HTTPException

    from app.edi_ingestion.extractors import _extract_856_fields
    from app.edi_ingestion.parser import _parse_x12_segments

    segments = _parse_x12_segments(_interchange_856_two_sn1_units("CA", "LB").decode())
    with pytest.raises(HTTPException) as exc:
        _extract_856_fields(segments)
    assert exc.value.detail["error"] == "edi_856_mixed_units_of_measure"


def test_two_unmappable_but_different_codes_still_refuse():
    """A code resolving to nothing keeps its raw form, so two different
    unmappable codes must not silently collapse into one unit."""
    from fastapi import HTTPException

    from app.edi_ingestion.extractors import _extract_856_fields
    from app.edi_ingestion.parser import _parse_x12_segments

    segments = _parse_x12_segments(_interchange_856_two_sn1_units("QQ", "ZZ").decode())
    with pytest.raises(HTTPException) as exc:
        _extract_856_fields(segments)
    assert exc.value.detail["error"] == "edi_856_mixed_units_of_measure"


def test_scalar_overrides_are_refused_for_a_batched_interchange(
    client: TestClient, captured_payload: dict
):
    """A scalar form override describes ONE shipment.

    Applying it across a batch would overwrite each transaction set's own
    extracted values with a single value — reintroducing, through the
    override path, exactly the cross-shipment field bleed #2976 fixes.
    Refuse rather than silently collapse.
    """
    raw = _interchange(
        [
            _856_set(control="0001", asn="ASN-A", ship_from="Valley Fresh Farms", bol="BOL-A"),
            _856_set(control="0002", asn="ASN-B", ship_from="Coastal Greens", bol="BOL-B"),
        ],
        isa13="000029912",
    )

    response = _post(
        client,
        raw,
        name="batch-with-override.edi",
        extra_data={"quantity_override": "42"},
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "edi_overrides_with_multiple_transaction_sets"
    assert detail["overrides"] == ["quantity_override"]
    assert detail["transaction_set_count"] == 2
    assert "payload" not in captured_payload, "nothing may land when overrides are refused"


def test_scalar_overrides_still_work_for_a_single_transaction_set(
    client: TestClient, captured_payload: dict
):
    """The guard must not break the ordinary single-shipment override path."""
    raw = _interchange(
        [_856_set(control="0001", asn="ASN-SOLO", ship_from="Valley Fresh Farms", bol="BOL-SOLO")],
        isa13="000029913",
    )

    response = _post(
        client,
        raw,
        name="single-with-override.edi",
        extra_data={"quantity_override": "42"},
    )

    assert response.status_code in (200, 201), response.text
    assert captured_payload["payload"].events[0].quantity == 42.0
