"""Focused unit tests for ``app.edi_ingestion.extractors``.

The extractors turn parsed X12 segment lists into plain field dicts for
each supported transaction set (856, 850, 810, 861) plus the shared
ISA/GS envelope helper and the ``_extract_fields_for_set`` dispatcher.
"""

from __future__ import annotations

import pytest
from app.edi_ingestion.extractors import (
    _apply_envelope_ids,
    _extract_810_fields,
    _extract_850_fields,
    _extract_856_fields,
    _extract_861_fields,
    _extract_envelope_ids,
    _extract_fields_for_set,
)
from fastapi import HTTPException


def _isa(sender="ISA_SENDER", receiver="ISA_RECEIVER", isa13="000000123"):
    return [
        "ISA",
        "00",
        "x",
        "00",
        "x",
        "ZZ",
        sender,
        "ZZ",
        receiver,
        "x",
        "x",
        "x",
        "00401",
        isa13,
        "x",
        "x",
        "x",
    ]


def _gs(sender="GS_SENDER", receiver="GS_RECEIVER", control="1"):
    return ["GS", "SH", sender, receiver, "20260310", "1200", control, "X", "004010"]


def _envelope(sender="GS_SENDER", receiver="GS_RECEIVER"):
    return [_isa(), _gs(sender, receiver)]


# ---------------------------------------------------------------------------
# Envelope helpers
# ---------------------------------------------------------------------------


def test_envelope_prefers_gs_over_isa():
    env = _extract_envelope_ids(_envelope())
    assert env["sender_id"] == "GS_SENDER"
    assert env["receiver_id"] == "GS_RECEIVER"
    assert env["isa_sender_id"] == "ISA_SENDER"
    assert env["gs_sender_id"] == "GS_SENDER"
    assert env["isa13"] == "000000123"
    assert env["gs_control_number"] == "1"
    assert env["envelope_mismatch"] is True


def test_envelope_matching_ids_have_no_mismatch():
    env = _extract_envelope_ids(_envelope("ISA_SENDER", "ISA_RECEIVER"))
    assert env["sender_id"] == "ISA_SENDER"
    assert env["envelope_mismatch"] is False


def test_envelope_falls_back_to_isa_when_gs_missing():
    env = _extract_envelope_ids([_isa()])
    assert env["sender_id"] == "ISA_SENDER"
    assert env["receiver_id"] == "ISA_RECEIVER"
    assert env["gs_sender_id"] is None
    assert env["envelope_mismatch"] is False


def test_envelope_empty_segments_yield_nones():
    env = _extract_envelope_ids([])
    assert env["sender_id"] is None
    assert env["receiver_id"] is None
    assert env["envelope_mismatch"] is False


def test_envelope_strips_fixed_width_padding():
    isa = _isa(sender="SENDER_ID      ", receiver="RECEIVER_ID    ")
    env = _extract_envelope_ids([isa, _gs("GS_SENDER", "GS_RECEIVER")])
    assert env["isa_sender_id"] == "SENDER_ID"
    assert env["isa_receiver_id"] == "RECEIVER_ID"


def test_apply_envelope_ids_populates_dict_in_place():
    data: dict = {}
    _apply_envelope_ids(data, _envelope())
    assert data["sender_id"] == "GS_SENDER"
    assert data["receiver_id"] == "GS_RECEIVER"
    assert data["isa13"] == "000000123"
    assert data["envelope_mismatch"] is True


# ---------------------------------------------------------------------------
# 856 (ship notice)
# ---------------------------------------------------------------------------


def _segments_856(sn1_lines=(("100", "CA"),), extra=()):
    segments = _envelope() + [
        ["ST", "856", "0001"],
        ["BSN", "00", "ASN123", "20260310", "1200"],
        ["N1", "SF", "SenderCo", "92", "shipper-gln"],
        ["N1", "ST", "ReceiverCo", "92", "receiver-gln"],
    ]
    for qty, uom in sn1_lines:
        segments.append(["SN1", "", qty, uom])
    segments += list(extra)
    return segments


def test_856_extracts_header_parties_and_control():
    data = _extract_856_fields(_segments_856())
    assert data["control_number"] == "0001"
    assert data["asn_number"] == "ASN123"
    assert data["ship_date_raw"] == "20260310"
    assert data["ship_time_raw"] == "1200"
    assert data["ship_from_name"] == "SenderCo"
    assert data["ship_to_name"] == "ReceiverCo"
    assert data["quantity"] == 100.0
    assert data["unit_of_measure"] == "CA"
    assert data["reference_document_number"] == "ASN123"
    assert data["sender_id"] == "GS_SENDER"


def test_856_accumulates_multiple_sn1_lines():
    data = _extract_856_fields(_segments_856(sn1_lines=(("100", "CA"), ("50", "CA"))))
    assert data["quantity"] == 150.0
    assert data["unit_of_measure"] == "CA"


def test_856_equivalent_unit_codes_sum_without_rejection():
    # CA and CS both resolve to "cases", so they must not raise.
    data = _extract_856_fields(_segments_856(sn1_lines=(("120", "CA"), ("80", "CS"))))
    assert data["quantity"] == 200.0


def test_856_mixed_units_raise_422():
    with pytest.raises(HTTPException) as exc_info:
        _extract_856_fields(_segments_856(sn1_lines=(("120", "CA"), ("80", "LB"))))
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "edi_856_mixed_units_of_measure"


def test_856_non_numeric_quantity_leaves_quantity_unset():
    data = _extract_856_fields(_segments_856(sn1_lines=(("abc", "CA"),)))
    assert data["quantity"] is None


def test_856_ref_and_carrier_and_description():
    segments = _segments_856(
        extra=[
            ["PID", "F", "", "", "", "Fresh romaine"],
            ["TD5", "", "", "ACME FREIGHT"],
            ["REF", "BM", "BOL999"],
        ]
    )
    data = _extract_856_fields(segments)
    assert data["product_description"] == "Fresh romaine"
    assert data["carrier"] == "ACME FREIGHT"
    assert data["reference_document_number"] == "BOL999"


# ---------------------------------------------------------------------------
# 850 (purchase order)
# ---------------------------------------------------------------------------


def test_850_extracts_po_header_parties_and_totals():
    segments = _envelope() + [
        ["ST", "850", "0002"],
        ["BEG", "00", "SA", "PO456", "", "20260310"],
        ["N1", "BY", "BuyerCo", "92", "buyer-gln"],
        ["N1", "SE", "SellerCo", "92", "seller-gln"],
        ["PO1", "1", "10", "EA", "2.50", "", "SK", "WIDGET-1"],
        ["PO1", "2", "5", "EA", "3.00"],
    ]
    data = _extract_850_fields(segments)
    assert data["control_number"] == "0002"
    assert data["po_number"] == "PO456"
    assert data["po_date_raw"] == "20260310"
    assert data["buyer_name"] == "BuyerCo"
    assert data["seller_name"] == "SellerCo"
    assert data["quantity"] == 15.0
    assert data["unit_of_measure"] == "EA"
    assert data["unit_price"] == "2.50"
    assert data["product_description"] == "WIDGET-1"
    assert data["reference_document_number"] == "PO456"


def test_850_empty_segments_keep_defaults():
    data = _extract_850_fields([])
    assert data["po_number"] is None
    assert data["quantity"] is None
    assert data["sender_id"] is None


# ---------------------------------------------------------------------------
# 810 (invoice)
# ---------------------------------------------------------------------------


def test_810_extracts_invoice_and_tds_total():
    segments = _envelope() + [
        ["ST", "810", "0003"],
        ["BIG", "20260310", "INV789", "", "PO456"],
        ["N1", "BY", "BuyerCo", "92", "buyer-gln"],
        ["N1", "SE", "SellerCo", "92", "seller-gln"],
        ["IT1", "1", "4", "EA", "9.99", "", "UP", "123456789012"],
        ["TDS", "109890"],
        ["REF", "PO", "PO456"],
    ]
    data = _extract_810_fields(segments)
    assert data["invoice_number"] == "INV789"
    assert data["invoice_date_raw"] == "20260310"
    assert data["po_number"] == "PO456"
    assert data["quantity"] == 4.0
    assert data["product_description"] == "123456789012"
    assert data["total_amount"] == pytest.approx(1098.90)
    assert data["reference_document_number"] == "INV789"


def test_810_bad_tds_leaves_total_unset():
    segments = _envelope() + [
        ["ST", "810", "0003"],
        ["BIG", "20260310", "INV789"],
        ["TDS", "not-a-number"],
    ]
    data = _extract_810_fields(segments)
    assert data["total_amount"] is None


# ---------------------------------------------------------------------------
# 861 (receiving advice)
# ---------------------------------------------------------------------------


def test_861_extracts_bra_rcd_and_po_ref():
    segments = _envelope() + [
        ["ST", "861", "0004"],
        ["BRA", "RA001", "20260311"],
        ["N1", "SF", "ShipperCo", "92", "shipper-gln"],
        ["N1", "ST", "WarehouseCo", "92", "warehouse-gln"],
        ["RCD", "", "25", "EA", "", "AA"],
        ["RCD", "", "10", "EA"],
        ["REF", "PO", "PO456"],
    ]
    data = _extract_861_fields(segments)
    assert data["control_number"] == "0004"
    assert data["receiving_advice_number"] == "RA001"
    assert data["receive_date_raw"] == "20260311"
    assert data["ship_from_name"] == "ShipperCo"
    assert data["receiving_location_name"] == "WarehouseCo"
    assert data["quantity"] == 35.0
    assert data["unit_of_measure"] == "EA"
    assert data["condition_code"] == "AA"
    assert data["po_number"] == "PO456"
    assert data["reference_document_number"] == "RA001"


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("transaction_set", "builder"),
    [
        ("856", _extract_856_fields),
        ("850", _extract_850_fields),
        ("810", _extract_810_fields),
        ("861", _extract_861_fields),
    ],
)
def test_dispatch_matches_direct_extractor(transaction_set, builder):
    segments = _envelope() + [["ST", transaction_set, "0001"]]
    assert _extract_fields_for_set(transaction_set, segments) == builder(segments)


def test_dispatch_unknown_set_returns_empty_dict():
    assert _extract_fields_for_set("999", _envelope()) == {}
