"""What makes two EDI lines the same line (ADR-007). No database.

Events are built two ways: by the real ``/document`` route from a synthetic
945, and directly, where a single field has to differ.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.edi_ingestion.routes as edi_routes  # noqa: E402
from app.authz import IngestionPrincipal, get_ingestion_principal  # noqa: E402
from app.edi_ingestion import router as edi_router  # noqa: E402
from app.edi_line_identity import identify_lines  # noqa: E402
from app.webhook_models import EventResult, IngestEvent, IngestResponse, WebhookCTEType  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.edi_documents import GTIN, TENANT, ship_notice, shipping_advice  # noqa: E402


@pytest.fixture()
def events_of(monkeypatch: pytest.MonkeyPatch):
    """Post a document to the real route and return the events it would store."""
    captured: list = []

    async def _capture(payload, **_):
        captured.append(payload)
        return IngestResponse(
            accepted=len(payload.events),
            rejected=0,
            total=len(payload.events),
            events=[
                EventResult(traceability_lot_code=e.traceability_lot_code, cte_type=e.cte_type.value, status="accepted")
                for e in payload.events
            ],
        )

    monkeypatch.setattr(edi_routes, "ingest_events", _capture)
    monkeypatch.setattr(edi_routes, "check_and_record_interchange", lambda *a, **k: (False, None))
    monkeypatch.delenv("EDI_REQUIRE_PARTNER_ID", raising=False)
    monkeypatch.delenv("EDI_PARTNER_ALLOWLIST", raising=False)
    app = FastAPI()
    app.include_router(edi_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key", scopes=["*"], auth_mode="test"
    )

    def _events(raw: bytes, route: str = "/document") -> list[IngestEvent]:
        captured.clear()
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/ingest/edi{route}",
                data={
                    "traceability_lot_code": f"{GTIN}-LOT001",
                    "tenant_id": TENANT,
                    "tlc_source_reference": "0061414100001",
                },
                files={"file": ("advice.edi", raw, "application/edi-x12")},
            )
        assert response.status_code == 201, response.text
        return list(captured[0].events)

    return _events


def _event(**changes) -> IngestEvent:
    """One 945-shaped line event. ``kdes`` in ``changes`` are merged, None removes."""
    kdes = {
        "edi_transaction_set": "945",
        "edi_sender_id": "SENDERID",
        "edi_receiver_id": "RECEIVERID",
        "edi_isa13": "000000201",
        "edi_gs_control_number": "1",
        "edi_control_number": "0001",
        "edi_line_index": 1,
        "shipment_id": "SHIP-9001",
        "depositor_order_number": "ORD-5001",
        "gtin": GTIN,
        "ship_to_location": "Metro Distribution Center",
    }
    for key, value in (changes.pop("kdes", None) or {}).items():
        if value is None:
            kdes.pop(key, None)
        else:
            kdes[key] = value
    fields = {
        "cte_type": WebhookCTEType.SHIPPING,
        "traceability_lot_code": f"{GTIN}-LOT-A",
        "product_description": "Romaine Hearts 12ct",
        "quantity": 40.0,
        "unit_of_measure": "cases",
        "location_gln": "6141410000014",
        "location_name": "Cold Storage West",
        "timestamp": "2026-03-10T00:00:00+00:00",
        "kdes": kdes,
    }
    fields.update(changes)
    return IngestEvent(**fields)


def _line(event: IngestEvent):
    (line,) = identify_lines([event])
    return line


def test_a_line_is_the_same_line_in_another_envelope_and_position(events_of) -> None:
    first = events_of(shipping_advice([("40", "LOT-A"), ("25", "LOT-B"), ("80", "LOT-C")]))
    resent = events_of(shipping_advice([("40", "LOT-A"), ("80", "LOT-C")], isa13="000000202", gs06="2", st02="0002"))

    assert [e.kdes["edi_line_index"] for e in first] == [1, 2, 3]
    assert [e.kdes["edi_line_index"] for e in resent] == [1, 2]
    # LOT-C moved from line 3 to line 2 and every envelope number changed.
    assert first[2].kdes["edi_isa13"] != resent[1].kdes["edi_isa13"]
    assert identify_lines(first)[2] == identify_lines(resent)[1]
    assert identify_lines(first)[0] == identify_lines(resent)[0]


def test_a_corrected_quantity_is_the_same_line_with_other_content(events_of) -> None:
    stored = identify_lines(events_of(shipping_advice([("40", "LOT-A"), ("25", "LOT-B")])))
    corrected = identify_lines(events_of(shipping_advice([("40", "LOT-A"), ("30", "LOT-B")], isa13="000000202")))

    assert corrected[0] == stored[0]
    assert corrected[1].identity_key == stored[1].identity_key
    assert corrected[1].content_digest != stored[1].content_digest


def test_identical_lines_are_numbered_so_both_persist(events_of) -> None:
    pair = identify_lines(events_of(shipping_advice([("40", "LOT-A"), ("40", "LOT-A")])))
    assert pair[0].identity_key != pair[1].identity_key
    assert pair[0].content_digest == pair[1].content_digest

    # Another lot in front does not renumber them.
    moved = identify_lines(events_of(shipping_advice([("9", "LOT-Z"), ("40", "LOT-A"), ("40", "LOT-A")])))
    assert moved[1:] == pair


def test_removing_the_first_of_two_same_lot_lines_reads_as_a_change() -> None:
    """Occurrence is counted among equal lines, so the survivor takes number 1.

    The registry then refuses it as changed content. That is the loud outcome
    ADR-007 accepts: nothing can tell a removed line from an edited one here.
    """
    both = identify_lines([_event(quantity=40.0), _event(quantity=25.0)])
    survivor = _line(_event(quantity=25.0))

    assert survivor.identity_key == both[0].identity_key
    assert survivor.content_digest != both[0].content_digest


@pytest.mark.parametrize(
    "kdes",
    [
        {"edi_sender_id": None},
        {"shipment_id": None, "depositor_order_number": None},
        {"edi_transaction_set": "999"},
    ],
)
def test_a_line_the_document_cannot_name_has_no_identity(kdes) -> None:
    assert _line(_event(kdes=kdes)) is None


def test_the_document_number_is_hashed_with_its_kind() -> None:
    by_shipment = _line(_event(kdes={"shipment_id": "5001", "depositor_order_number": "ORD-1"}))
    by_order = _line(_event(kdes={"shipment_id": None, "depositor_order_number": "5001"}))
    assert by_shipment.identity_key != by_order.identity_key
    # The shipment id names the line while present. The order number is then content.
    other_order = _line(_event(kdes={"shipment_id": "5001", "depositor_order_number": "ORD-2"}))
    assert other_order.identity_key == by_shipment.identity_key
    assert other_order.content_digest != by_shipment.content_digest


@pytest.mark.parametrize(
    "transaction_set,kde",
    [
        ("856", "asn_number"),
        ("861", "receiving_advice_number"),
        ("944", "warehouse_receipt_number"),
        ("850", "po_number"),
        ("810", "invoice_number"),
    ],
)
def test_every_supported_set_has_a_document_number(transaction_set: str, kde: str) -> None:
    kdes = {"edi_transaction_set": transaction_set, "shipment_id": None, "depositor_order_number": None}
    assert _line(_event(kdes=kdes)) is None
    assert _line(_event(kdes={**kdes, kde: "DOC-1"})) is not None


@pytest.mark.parametrize(
    "kdes",
    [
        {"edi_isa13": "000000999"},
        {"edi_gs_control_number": "77"},
        {"edi_control_number": "0042"},
        {"edi_line_index": 9},
        {"edi_isa_sender_id": "SENDERID", "edi_gs_sender_id": "SENDERID"},
        {"partner_id": "WALMART"},
    ],
)
def test_envelope_and_position_are_neither_identity_nor_content(kdes) -> None:
    assert _line(_event(kdes=kdes)) == _line(_event())


@pytest.mark.parametrize(
    "kdes",
    [
        {"event_date": "2026-03-10"},
        {"ship_date": "2026-03-10"},
        {"receive_date": "2026-03-10"},
        {"immediate_previous_source": "Cold Storage West"},
    ],
)
def test_kdes_that_restate_the_date_or_the_ship_from_party_are_not_content(kdes) -> None:
    """They repeat the timestamp or the ship-from fields, which are compared."""
    assert _line(_event(kdes=kdes)) == _line(_event())


@pytest.mark.parametrize(
    "lines",
    [
        [("ROMAINE-12CT", "200", "LOT-A")],
        [("ROMAINE-12CT", "200", "LOT-A"), ("SPINACH-10OZ", "80", "LOT-B"), ("ROMAINE-12CT", "200", "LOT-A")],
    ],
)
def test_both_856_routes_describe_a_line_the_same_way(events_of, lines) -> None:
    """One file, either endpoint: the same identity and the same content.

    The two routes build their events separately and name some KDEs
    differently. If they stop agreeing here, a line stored through one route
    and sent again through the other is stored twice (identity differs) or
    refused with ``edi_line_content_conflict`` (content differs). Align the
    two builders, or leave a KDE out of the comparison on purpose.
    """
    raw = ship_notice(lines)
    dedicated = identify_lines(events_of(raw, route=""))
    document = identify_lines(events_of(raw))

    assert len(dedicated) == len(lines)
    assert dedicated == document


@pytest.mark.parametrize(
    "changes",
    [
        {"quantity": 41.0},
        {"unit_of_measure": "lbs"},
        {"location_name": "Cold Storage East"},
        {"timestamp": "2026-03-10T08:30:00+00:00"},
        {"kdes": {"ship_to_location": "Metro DC 2"}},
        {"kdes": {"carrier": "ColdExpress"}},
    ],
)
def test_everything_else_is_content(changes) -> None:
    line, base = _line(_event(**changes)), _line(_event())
    assert line.identity_key == base.identity_key
    assert line.content_digest != base.content_digest


@pytest.mark.parametrize(
    "changes",
    [
        {"timestamp": "2026-03-11T00:00:00+00:00"},
        {"traceability_lot_code": f"{GTIN}-LOT-B"},
        {"cte_type": WebhookCTEType.RECEIVING},
        {"kdes": {"gtin": "00012345678912"}},
        {"kdes": {"edi_receiver_id": "OTHERDC"}},
    ],
)
def test_another_date_lot_event_product_or_partner_is_another_line(changes) -> None:
    assert _line(_event(**changes)).identity_key != _line(_event()).identity_key


def test_the_lot_code_is_identity_exactly_as_stored() -> None:
    """Both stores keep lot codes that differ only in whitespace apart.

    If the identity folded them, the second would be reported as already
    stored and never written.
    """
    padded = _event(traceability_lot_code=f" {GTIN}-LOT-A ")
    assert padded.traceability_lot_code == f" {GTIN}-LOT-A "
    assert _line(padded).identity_key != _line(_event()).identity_key
    assert _line(padded).content_digest == _line(_event()).content_digest


def test_product_text_is_compared_without_case_or_spacing() -> None:
    def named(text: str):
        return _line(_event(product_description=text, kdes={"gtin": None}))

    assert named("Romaine  Hearts 12CT").identity_key == named("romaine hearts 12ct").identity_key
    assert named("Romaine Hearts 24ct").identity_key != named("romaine hearts 12ct").identity_key


def test_identity_and_content_digest_are_pinned() -> None:
    """These two values are what a resend is compared with.

    If this fails, the meaning of "the same line" or "the same content" has
    changed. Lines stored before the change will then stop matching: an
    identity change stores them again, a content change refuses them with 409
    ``edi_line_content_conflict``. Change the pins only if that is intended,
    and say so in the pull request.

    The event here is built by hand, so this covers the identity and content
    rules only. The next test covers what the route feeds into them.
    """
    identity = "9963d3511d2a9c4df950b4475ab64f5c24ac435fd7b055007fb855751a2cfbde"  # pragma: allowlist secret
    content = "6642e24c4e12e17c03c5064215052a20cd956ba215d5f39a96ac3495dc38599c"  # pragma: allowlist secret
    line = _line(_event())
    assert line.identity_key == identity
    assert line.content_digest == content


def test_lines_built_by_the_route_are_pinned(events_of) -> None:
    """The same pins for one 945 line and one 856 line as the real route builds them.

    The test above pins the identity and content rules. This one also covers
    extraction and KDE mapping for these two sets: change how a segment is
    read, or which KDEs the route emits, and a value here moves. The other
    sets (861, 944, 850, 810) are not pinned.
    """
    advice_identity = "9963d3511d2a9c4df950b4475ab64f5c24ac435fd7b055007fb855751a2cfbde"  # pragma: allowlist secret
    advice_content = "69dc48d2985a7663615606c32b975bc8933c45dba46541e66582c6bc51957966"  # pragma: allowlist secret
    notice_identity = "e14a424fcb7da5bc082708b89017dd014d0f995f645fca7ad34db4d24fcbbc1d"  # pragma: allowlist secret
    notice_content = "6cb9bceac82cb16624466d5a69b2a4dba528bb45d706317da367566791a06db3"  # pragma: allowlist secret
    advice = identify_lines(events_of(shipping_advice([("40", "LOT-A")])))[0]
    notice = identify_lines(events_of(ship_notice([("ROMAINE-12CT", "200", "LOT-A")])))[0]
    assert (advice.identity_key, advice.content_digest) == (advice_identity, advice_content)
    assert (notice.identity_key, notice.content_digest) == (notice_identity, notice_content)
