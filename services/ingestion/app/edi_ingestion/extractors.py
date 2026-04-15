from __future__ import annotations

from typing import Any

from .constants import _FROM_ENTITY_CODES, _TO_ENTITY_CODES
from .parser import _first_segment
from .utils import _safe_float


def _extract_856_fields(segments: list[list[str]]) -> dict[str, Any]:
    data: dict[str, Any] = {
        "sender_id": None,
        "receiver_id": None,
        "control_number": None,
        "asn_number": None,
        "ship_date_raw": None,
        "ship_time_raw": None,
        "ship_from_name": None,
        "ship_from_gln": None,
        "ship_to_name": None,
        "ship_to_gln": None,
        "quantity": None,
        "unit_of_measure": None,
        "product_description": None,
        "reference_document_number": None,
        "carrier": None,
    }

    isa = _first_segment(segments, "ISA")
    if isa:
        data["sender_id"] = isa[6] if len(isa) > 6 else None
        data["receiver_id"] = isa[8] if len(isa) > 8 else None

    st = _first_segment(segments, "ST")
    if st and len(st) > 2:
        data["control_number"] = st[2]

    bsn = _first_segment(segments, "BSN")
    if bsn:
        data["asn_number"] = bsn[2] if len(bsn) > 2 else None
        data["ship_date_raw"] = bsn[3] if len(bsn) > 3 else None
        data["ship_time_raw"] = bsn[4] if len(bsn) > 4 else None

    for segment in segments:
        if not segment:
            continue
        seg_id = segment[0].upper()

        if seg_id == "N1":
            entity_code = segment[1].upper() if len(segment) > 1 else ""
            name = segment[2] if len(segment) > 2 and segment[2] else None
            location_id = segment[4] if len(segment) > 4 and segment[4] else None

            if entity_code in _FROM_ENTITY_CODES:
                data["ship_from_name"] = data["ship_from_name"] or name
                data["ship_from_gln"] = data["ship_from_gln"] or location_id
            elif entity_code in _TO_ENTITY_CODES:
                data["ship_to_name"] = data["ship_to_name"] or name
                data["ship_to_gln"] = data["ship_to_gln"] or location_id

        elif seg_id == "SN1":
            if len(segment) > 2 and segment[2]:
                data["quantity"] = _safe_float(segment[2], fallback=1.0)
            if len(segment) > 3 and segment[3]:
                data["unit_of_measure"] = segment[3]

        elif seg_id == "PID":
            if len(segment) > 5 and segment[5]:
                data["product_description"] = data["product_description"] or segment[5]

        elif seg_id == "LIN":
            for idx in range(1, len(segment) - 1):
                qualifier = segment[idx].upper()
                if qualifier in {"SK", "UP", "EN", "VP", "BP"} and segment[idx + 1]:
                    data["product_description"] = data["product_description"] or segment[idx + 1]
                    break

        elif seg_id == "REF":
            if len(segment) > 2 and segment[2]:
                qualifier = segment[1].upper() if len(segment) > 1 else ""
                if qualifier in {"BM", "SI", "CN", "PO", "PK"}:
                    data["reference_document_number"] = (
                        data["reference_document_number"] or segment[2]
                    )

        elif seg_id == "TD5":
            # Favor carrier name/code if present in routing details.
            for candidate in segment[2:]:
                if candidate:
                    data["carrier"] = data["carrier"] or candidate
                    if data["carrier"]:
                        break

    if not data["reference_document_number"]:
        data["reference_document_number"] = data["asn_number"]

    return data


def _extract_850_fields(segments: list[list[str]]) -> dict[str, Any]:
    """Extract fields from X12 850 Purchase Order."""
    data: dict[str, Any] = {
        "sender_id": None,
        "receiver_id": None,
        "control_number": None,
        "po_number": None,
        "po_date_raw": None,
        "buyer_name": None,
        "buyer_gln": None,
        "seller_name": None,
        "seller_gln": None,
        "quantity": None,
        "unit_of_measure": None,
        "product_description": None,
        "unit_price": None,
        "reference_document_number": None,
    }

    isa = _first_segment(segments, "ISA")
    if isa:
        data["sender_id"] = isa[6] if len(isa) > 6 else None
        data["receiver_id"] = isa[8] if len(isa) > 8 else None

    st = _first_segment(segments, "ST")
    if st and len(st) > 2:
        data["control_number"] = st[2]

    beg = _first_segment(segments, "BEG")
    if beg:
        data["po_number"] = beg[3] if len(beg) > 3 else None
        data["po_date_raw"] = beg[5] if len(beg) > 5 else None

    data["reference_document_number"] = data["po_number"]

    total_quantity = 0.0
    for segment in segments:
        if not segment:
            continue
        seg_id = segment[0].upper()

        if seg_id == "N1":
            entity_code = segment[1].upper() if len(segment) > 1 else ""
            name = segment[2] if len(segment) > 2 and segment[2] else None
            location_id = segment[4] if len(segment) > 4 and segment[4] else None
            if entity_code in {"BY", "BT"}:
                data["buyer_name"] = data["buyer_name"] or name
                data["buyer_gln"] = data["buyer_gln"] or location_id
            elif entity_code in {"SE", "SU", "VN"}:
                data["seller_name"] = data["seller_name"] or name
                data["seller_gln"] = data["seller_gln"] or location_id

        elif seg_id == "PO1":
            if len(segment) > 2 and segment[2]:
                total_quantity += _safe_float(segment[2], fallback=0.0)
            if len(segment) > 3 and segment[3]:
                data["unit_of_measure"] = data["unit_of_measure"] or segment[3]
            if len(segment) > 4 and segment[4]:
                data["unit_price"] = data["unit_price"] or segment[4]
            # Product identifier in qualifier/value pairs
            for idx in range(6, len(segment) - 1, 2):
                qualifier = segment[idx].upper() if segment[idx] else ""
                if qualifier in {"SK", "UP", "EN", "VP", "BP", "IN"} and segment[idx + 1]:
                    data["product_description"] = data["product_description"] or segment[idx + 1]
                    break

        elif seg_id == "PID":
            if len(segment) > 5 and segment[5]:
                data["product_description"] = data["product_description"] or segment[5]

    if total_quantity > 0:
        data["quantity"] = total_quantity

    return data


def _extract_810_fields(segments: list[list[str]]) -> dict[str, Any]:
    """Extract fields from X12 810 Invoice."""
    data: dict[str, Any] = {
        "sender_id": None,
        "receiver_id": None,
        "control_number": None,
        "invoice_number": None,
        "invoice_date_raw": None,
        "po_number": None,
        "buyer_name": None,
        "buyer_gln": None,
        "seller_name": None,
        "seller_gln": None,
        "quantity": None,
        "unit_of_measure": None,
        "product_description": None,
        "total_amount": None,
        "reference_document_number": None,
    }

    isa = _first_segment(segments, "ISA")
    if isa:
        data["sender_id"] = isa[6] if len(isa) > 6 else None
        data["receiver_id"] = isa[8] if len(isa) > 8 else None

    st = _first_segment(segments, "ST")
    if st and len(st) > 2:
        data["control_number"] = st[2]

    big = _first_segment(segments, "BIG")
    if big:
        data["invoice_date_raw"] = big[1] if len(big) > 1 else None
        data["invoice_number"] = big[2] if len(big) > 2 else None
        data["po_number"] = big[4] if len(big) > 4 and big[4] else None

    data["reference_document_number"] = data["invoice_number"]

    total_quantity = 0.0
    for segment in segments:
        if not segment:
            continue
        seg_id = segment[0].upper()

        if seg_id == "N1":
            entity_code = segment[1].upper() if len(segment) > 1 else ""
            name = segment[2] if len(segment) > 2 and segment[2] else None
            location_id = segment[4] if len(segment) > 4 and segment[4] else None
            if entity_code in {"BY", "BT", "RI"}:
                data["buyer_name"] = data["buyer_name"] or name
                data["buyer_gln"] = data["buyer_gln"] or location_id
            elif entity_code in {"SE", "SU", "VN", "SF"}:
                data["seller_name"] = data["seller_name"] or name
                data["seller_gln"] = data["seller_gln"] or location_id

        elif seg_id == "IT1":
            if len(segment) > 2 and segment[2]:
                total_quantity += _safe_float(segment[2], fallback=0.0)
            if len(segment) > 3 and segment[3]:
                data["unit_of_measure"] = data["unit_of_measure"] or segment[3]
            for idx in range(6, len(segment) - 1, 2):
                qualifier = segment[idx].upper() if segment[idx] else ""
                if qualifier in {"SK", "UP", "EN", "VP", "IN"} and segment[idx + 1]:
                    data["product_description"] = data["product_description"] or segment[idx + 1]
                    break

        elif seg_id == "PID":
            if len(segment) > 5 and segment[5]:
                data["product_description"] = data["product_description"] or segment[5]

        elif seg_id == "TDS":
            if len(segment) > 1 and segment[1]:
                try:
                    data["total_amount"] = float(segment[1]) / 100.0
                except (ValueError, TypeError):
                    pass

        elif seg_id == "REF":
            if len(segment) > 2 and segment[2]:
                qualifier = segment[1].upper() if len(segment) > 1 else ""
                if qualifier in {"PO", "VN", "IV"}:
                    if qualifier == "PO":
                        data["po_number"] = data["po_number"] or segment[2]

    if total_quantity > 0:
        data["quantity"] = total_quantity

    return data


def _extract_861_fields(segments: list[list[str]]) -> dict[str, Any]:
    """Extract fields from X12 861 Receiving Advice."""
    data: dict[str, Any] = {
        "sender_id": None,
        "receiver_id": None,
        "control_number": None,
        "receiving_advice_number": None,
        "receive_date_raw": None,
        "po_number": None,
        "ship_from_name": None,
        "ship_from_gln": None,
        "receiving_location_name": None,
        "receiving_location_gln": None,
        "quantity": None,
        "unit_of_measure": None,
        "product_description": None,
        "reference_document_number": None,
        "condition_code": None,
    }

    isa = _first_segment(segments, "ISA")
    if isa:
        data["sender_id"] = isa[6] if len(isa) > 6 else None
        data["receiver_id"] = isa[8] if len(isa) > 8 else None

    st = _first_segment(segments, "ST")
    if st and len(st) > 2:
        data["control_number"] = st[2]

    bra = _first_segment(segments, "BRA")
    if bra:
        data["receiving_advice_number"] = bra[2] if len(bra) > 2 else None
        data["receive_date_raw"] = bra[3] if len(bra) > 3 else None

    data["reference_document_number"] = data["receiving_advice_number"]

    total_quantity = 0.0
    for segment in segments:
        if not segment:
            continue
        seg_id = segment[0].upper()

        if seg_id == "N1":
            entity_code = segment[1].upper() if len(segment) > 1 else ""
            name = segment[2] if len(segment) > 2 and segment[2] else None
            location_id = segment[4] if len(segment) > 4 and segment[4] else None
            if entity_code in _FROM_ENTITY_CODES:
                data["ship_from_name"] = data["ship_from_name"] or name
                data["ship_from_gln"] = data["ship_from_gln"] or location_id
            elif entity_code in _TO_ENTITY_CODES:
                data["receiving_location_name"] = data["receiving_location_name"] or name
                data["receiving_location_gln"] = data["receiving_location_gln"] or location_id

        elif seg_id == "RCD":
            if len(segment) > 2 and segment[2]:
                total_quantity += _safe_float(segment[2], fallback=0.0)
            if len(segment) > 3 and segment[3]:
                data["unit_of_measure"] = data["unit_of_measure"] or segment[3]
            if len(segment) > 5 and segment[5]:
                data["condition_code"] = data["condition_code"] or segment[5]

        elif seg_id == "LIN":
            for idx in range(1, len(segment) - 1):
                qualifier = segment[idx].upper()
                if qualifier in {"SK", "UP", "EN", "VP", "BP"} and segment[idx + 1]:
                    data["product_description"] = data["product_description"] or segment[idx + 1]
                    break

        elif seg_id == "PID":
            if len(segment) > 5 and segment[5]:
                data["product_description"] = data["product_description"] or segment[5]

        elif seg_id == "REF":
            if len(segment) > 2 and segment[2]:
                qualifier = segment[1].upper() if len(segment) > 1 else ""
                if qualifier in {"PO", "BM", "SI"}:
                    if qualifier == "PO":
                        data["po_number"] = data["po_number"] or segment[2]
                    data["reference_document_number"] = (
                        data["reference_document_number"] or segment[2]
                    )

    if total_quantity > 0:
        data["quantity"] = total_quantity

    return data


def _extract_fields_for_set(transaction_set: str, segments: list[list[str]]) -> dict[str, Any]:
    """Dispatch to the correct field extractor based on transaction set."""
    if transaction_set == "856":
        return _extract_856_fields(segments)
    elif transaction_set == "850":
        return _extract_850_fields(segments)
    elif transaction_set == "810":
        return _extract_810_fields(segments)
    elif transaction_set == "861":
        return _extract_861_fields(segments)
    return {}
