from __future__ import annotations

from math import isfinite
from typing import Any

from .constants import _FROM_ENTITY_CODES, _TO_ENTITY_CODES
from .parser import _first_segment
from .utils import _safe_float


def _extract_envelope_ids(segments: list[list[str]]) -> dict[str, Any]:
    """Extract ISA + GS envelope identifiers (#1160, #1165).

    Returns a dict containing:
      - ``isa_sender_id``  (ISA[6])
      - ``isa_receiver_id`` (ISA[8])
      - ``isa13``           (ISA[13] — interchange control number, used for
                            retransmission deduplication, #1165)
      - ``gs_sender_id``    (GS[2] — application sender, #1160: the true
                            trading-partner identity, not ISA)
      - ``gs_receiver_id``  (GS[3])
      - ``gs_control_number`` (GS[6])
      - ``sender_id``       (GS sender_id first, ISA fallback — the
                            canonical trading-partner identifier)
      - ``receiver_id``     (same logic for receiver)
      - ``envelope_mismatch`` bool — True when ISA and GS disagree on
                                    sender or receiver. Callers should
                                    reject rather than pick arbitrarily.
    """
    isa = _first_segment(segments, "ISA") or []
    gs = _first_segment(segments, "GS") or []

    isa_sender = (isa[6] if len(isa) > 6 else None) or None
    isa_receiver = (isa[8] if len(isa) > 8 else None) or None
    isa13 = (isa[13] if len(isa) > 13 else None) or None

    gs_sender = (gs[2] if len(gs) > 2 else None) or None
    gs_receiver = (gs[3] if len(gs) > 3 else None) or None
    gs_control_number = (gs[6] if len(gs) > 6 else None) or None

    # Strip whitespace — X12 envelope fields are fixed-width and right-padded.
    def _strip(v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v

    isa_sender = _strip(isa_sender)
    isa_receiver = _strip(isa_receiver)
    isa13 = _strip(isa13)
    gs_sender = _strip(gs_sender)
    gs_receiver = _strip(gs_receiver)
    gs_control_number = _strip(gs_control_number)

    envelope_mismatch = False
    if gs_sender and isa_sender and gs_sender != isa_sender:
        envelope_mismatch = True
    if gs_receiver and isa_receiver and gs_receiver != isa_receiver:
        envelope_mismatch = True

    return {
        "isa_sender_id": isa_sender,
        "isa_receiver_id": isa_receiver,
        "isa13": isa13,
        "gs_sender_id": gs_sender,
        "gs_receiver_id": gs_receiver,
        "gs_control_number": gs_control_number,
        # Canonical trading-partner identity: GS wins over ISA per X12 spec.
        "sender_id": gs_sender or isa_sender,
        "receiver_id": gs_receiver or isa_receiver,
        "envelope_mismatch": envelope_mismatch,
    }


# Item identifiers that become the line's product description. LT is the
# lot and is never folded into that description.
_ITEM_ID_QUALIFIERS = {"SK", "UP", "EN", "VP", "BP"}


def _segment_value(segment: list[str], index: int) -> str | None:
    if len(segment) <= index:
        return None
    value = segment[index].strip()
    return value or None


def _positive_line_quantity(raw: str | None) -> float | None:
    """A line quantity is unset unless the element is a finite number above 0.

    ``_safe_float``'s 0.0 fallback is what keeps a blank or non-numeric
    SN1/RCD from inventing a quantity. The route then refuses that line
    instead of synthesizing 1.0.
    """
    if not raw:
        return None
    quantity = _safe_float(raw, fallback=0.0)
    if isfinite(quantity) and quantity > 0:
        return quantity
    return None


def _apply_id_pairs(target: dict[str, Any], segment: list[str], start: int) -> None:
    for index in range(start, len(segment) - 1, 2):
        qualifier = segment[index].strip().upper()
        value = segment[index + 1].strip()
        if not qualifier or not value:
            continue
        if qualifier == "LT":
            target["lot_number"] = target["lot_number"] or value
        elif qualifier in _ITEM_ID_QUALIFIERS:
            target["product_description"] = target["product_description"] or value


class _ItemLines:
    """One CTE draft per SN1 or RCD, with lot and product from that item.

    A LIN before the quantity segment fills the draft the next SN1/RCD
    copies. A LIN after a quantity segment that still has no product and
    no lot fills that line (861 often sends RCD, then LIN). A later LIN
    starts the next item. PID, REF*LT, and an SLN LT qualifier attach to
    the open line, or to the draft when no line is open yet. SLN itself
    is not a CTE.
    """

    def __init__(self) -> None:
        self.item: dict[str, Any] = {
            "product_description": None,
            "lot_number": None,
        }
        self.lines: list[dict[str, Any]] = []
        self._open: int | None = None

    def add_lin(self, segment: list[str]) -> None:
        if self._open is not None:
            line = self.lines[self._open]
            if not line["product_description"] and not line["lot_number"]:
                _apply_id_pairs(line, segment, 2)
                self._open = None
                self.item = {"product_description": None, "lot_number": None}
                return
            self.item = {"product_description": None, "lot_number": None}
            self._open = None
        _apply_id_pairs(self.item, segment, 2)

    def add_description(self, text: str | None) -> None:
        if not text:
            return
        if self._open is not None:
            line = self.lines[self._open]
            line["product_description"] = line["product_description"] or text
        else:
            self.item["product_description"] = self.item["product_description"] or text

    def add_lot(self, lot: str | None) -> None:
        if not lot:
            return
        if self._open is not None:
            line = self.lines[self._open]
            line["lot_number"] = line["lot_number"] or lot
        else:
            self.item["lot_number"] = self.item["lot_number"] or lot

    def add_sln(self, segment: list[str]) -> None:
        # SLN product-id pairs start at SLN09.
        if self._open is not None:
            _apply_id_pairs(self.lines[self._open], segment, 9)
        else:
            _apply_id_pairs(self.item, segment, 9)

    def commit(self, segment: list[str], *, condition_index: int | None = None) -> None:
        line: dict[str, Any] = {
            "quantity": _positive_line_quantity(_segment_value(segment, 2)),
            "unit_of_measure": _segment_value(segment, 3),
            "product_description": self.item["product_description"],
            "lot_number": self.item["lot_number"],
        }
        if condition_index is not None:
            line["condition_code"] = _segment_value(segment, condition_index)
        self.lines.append(line)
        self._open = len(self.lines) - 1


def _apply_envelope_ids(data: dict[str, Any], segments: list[list[str]]) -> None:
    """Populate envelope fields on an extraction dict in-place."""
    envelope = _extract_envelope_ids(segments)
    data["sender_id"] = envelope["sender_id"]
    data["receiver_id"] = envelope["receiver_id"]
    data["isa_sender_id"] = envelope["isa_sender_id"]
    data["isa_receiver_id"] = envelope["isa_receiver_id"]
    data["gs_sender_id"] = envelope["gs_sender_id"]
    data["gs_receiver_id"] = envelope["gs_receiver_id"]
    data["isa13"] = envelope["isa13"]
    data["gs_control_number"] = envelope["gs_control_number"]
    data["envelope_mismatch"] = envelope["envelope_mismatch"]


def _extract_856_fields(segments: list[list[str]]) -> dict[str, Any]:
    data: dict[str, Any] = {
        "sender_id": None,
        "receiver_id": None,
        "isa_sender_id": None,
        "isa_receiver_id": None,
        "gs_sender_id": None,
        "gs_receiver_id": None,
        "isa13": None,
        "gs_control_number": None,
        "envelope_mismatch": False,
        "control_number": None,
        "asn_number": None,
        "ship_date_raw": None,
        "ship_time_raw": None,
        "ship_from_name": None,
        "ship_from_gln": None,
        "ship_to_name": None,
        "ship_to_gln": None,
        "reference_document_number": None,
        "carrier": None,
        "line_items": [],
    }

    _apply_envelope_ids(data, segments)

    st = _first_segment(segments, "ST")
    if st and len(st) > 2:
        data["control_number"] = st[2]

    bsn = _first_segment(segments, "BSN")
    if bsn:
        data["asn_number"] = bsn[2] if len(bsn) > 2 else None
        data["ship_date_raw"] = bsn[3] if len(bsn) > 3 else None
        data["ship_time_raw"] = bsn[4] if len(bsn) > 4 else None

    items = _ItemLines()
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
            items.commit(segment)

        elif seg_id == "PID":
            items.add_description(_segment_value(segment, 5))

        elif seg_id == "LIN":
            items.add_lin(segment)

        elif seg_id == "SLN":
            items.add_sln(segment)

        elif seg_id == "REF":
            if len(segment) > 2 and segment[2]:
                qualifier = segment[1].upper() if len(segment) > 1 else ""
                if qualifier == "LT":
                    items.add_lot(segment[2].strip())
                elif qualifier in {"BM", "SI", "CN", "PO", "PK"}:
                    data["reference_document_number"] = data["reference_document_number"] or segment[2]

        elif seg_id == "TD5":
            # Favor carrier name/code if present in routing details.
            for candidate in segment[2:]:
                if candidate:
                    data["carrier"] = data["carrier"] or candidate
                    if data["carrier"]:
                        break

    data["line_items"] = items.lines

    if not data["reference_document_number"]:
        data["reference_document_number"] = data["asn_number"]

    return data


def _extract_850_fields(segments: list[list[str]]) -> dict[str, Any]:
    """Extract fields from X12 850 Purchase Order."""
    data: dict[str, Any] = {
        "sender_id": None,
        "receiver_id": None,
        "isa_sender_id": None,
        "isa_receiver_id": None,
        "gs_sender_id": None,
        "gs_receiver_id": None,
        "isa13": None,
        "gs_control_number": None,
        "envelope_mismatch": False,
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

    _apply_envelope_ids(data, segments)

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

        elif seg_id == "REF":
            # A PO number sent only via REF*PO (BEG without BEG03) must
            # still link the CTE, mirroring the 861 extractor.
            if len(segment) > 2 and segment[2]:
                qualifier = segment[1].upper() if len(segment) > 1 else ""
                if qualifier == "PO":
                    data["po_number"] = data["po_number"] or segment[2]

    if not data["reference_document_number"]:
        data["reference_document_number"] = data["po_number"]

    if total_quantity > 0:
        data["quantity"] = total_quantity

    return data


def _extract_810_fields(segments: list[list[str]]) -> dict[str, Any]:
    """Extract fields from X12 810 Invoice."""
    data: dict[str, Any] = {
        "sender_id": None,
        "receiver_id": None,
        "isa_sender_id": None,
        "isa_receiver_id": None,
        "gs_sender_id": None,
        "gs_receiver_id": None,
        "isa13": None,
        "gs_control_number": None,
        "envelope_mismatch": False,
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

    _apply_envelope_ids(data, segments)

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
        "isa_sender_id": None,
        "isa_receiver_id": None,
        "gs_sender_id": None,
        "gs_receiver_id": None,
        "isa13": None,
        "gs_control_number": None,
        "envelope_mismatch": False,
        "control_number": None,
        "receiving_advice_number": None,
        "receive_date_raw": None,
        "po_number": None,
        "ship_from_name": None,
        "ship_from_gln": None,
        "receiving_location_name": None,
        "receiving_location_gln": None,
        "reference_document_number": None,
        "line_items": [],
    }

    _apply_envelope_ids(data, segments)

    st = _first_segment(segments, "ST")
    if st and len(st) > 2:
        data["control_number"] = st[2]

    bra = _first_segment(segments, "BRA")
    if bra:
        # BRA01 is the reference identification and BRA02 the date; unlike
        # BSN01/BEG01 the purpose code sits at BRA03, per X12 spec.
        data["receiving_advice_number"] = bra[1] if len(bra) > 1 else None
        data["receive_date_raw"] = bra[2] if len(bra) > 2 else None

    data["reference_document_number"] = data["receiving_advice_number"]

    items = _ItemLines()
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
            # RCD[5] is the condition code this extractor has always read.
            items.commit(segment, condition_index=5)

        elif seg_id == "LIN":
            items.add_lin(segment)

        elif seg_id == "SLN":
            items.add_sln(segment)

        elif seg_id == "PID":
            items.add_description(_segment_value(segment, 5))

        elif seg_id == "REF":
            if len(segment) > 2 and segment[2]:
                qualifier = segment[1].upper() if len(segment) > 1 else ""
                if qualifier == "LT":
                    items.add_lot(segment[2].strip())
                elif qualifier in {"PO", "BM", "SI"}:
                    if qualifier == "PO":
                        data["po_number"] = data["po_number"] or segment[2]
                    data["reference_document_number"] = data["reference_document_number"] or segment[2]

    data["line_items"] = items.lines

    return data


def _element(segment: list[str], index: int) -> str | None:
    """Return a stripped element, or None when it is missing or blank."""
    if len(segment) <= index:
        return None
    value = segment[index].strip()
    return value or None


# Product-id qualifiers on W07 and W12. UP is a UPC. The rest are GTIN-style.
# SKU-like qualifiers fill the description only when no G69 text is present.
_GTIN_QUALIFIERS = {"UK", "EN", "UI", "UA", "EO"}
_UPC_QUALIFIERS = {"UP"}
_SKU_QUALIFIERS = {"SK", "VN", "BP", "IN", "VP", "PI"}

# W07 product-id pairs are (04,05), (06,07), (18,19) and (20,21).
# W0708 (index 8) is the warehouse lot and must not be read as a qualifier.
_W07_PRODUCT_PAIRS = ((4, 5), (6, 7), (18, 19), (20, 21))
# W12 pairs are (07,08), (19,20) and (21,22). W1209 (index 9) is the lot.
_W12_PRODUCT_PAIRS = ((7, 8), (19, 20), (21, 22))


def _keep_first(data: dict[str, Any], key: str, value: str | None) -> None:
    if value:
        data[key] = data[key] or value


def _apply_product_id(data: dict[str, Any], qualifier: str | None, value: str | None) -> None:
    if not qualifier or not value:
        return
    code = qualifier.upper()
    if code in _UPC_QUALIFIERS:
        data["upc"] = data["upc"] or value
    elif code in _GTIN_QUALIFIERS:
        data["gtin"] = data["gtin"] or value
    elif code in _SKU_QUALIFIERS:
        data["product_description"] = data["product_description"] or value


def _apply_product_pairs(
    data: dict[str, Any],
    segment: list[str],
    pairs: tuple[tuple[int, int], ...],
) -> None:
    for qualifier_index, value_index in pairs:
        _apply_product_id(data, _element(segment, qualifier_index), _element(segment, value_index))


def _apply_n9(data: dict[str, Any], segment: list[str]) -> None:
    qualifier = (_element(segment, 1) or "").upper()
    value = _element(segment, 2)
    if not qualifier or not value:
        return
    data["reference_numbers"].setdefault(qualifier, value)
    if qualifier == "PO":
        data["po_number"] = data["po_number"] or value
    elif qualifier == "BM":
        data["bill_of_lading"] = data["bill_of_lading"] or value


def _note_g62(data: dict[str, Any], segment: list[str], header_date_field: str) -> None:
    """Record G62. Use it as the event date only when the header date is empty."""
    qualifier = _element(segment, 1)
    date_value = _element(segment, 2)
    if qualifier:
        data["g62_date_qualifier"] = data["g62_date_qualifier"] or qualifier
    if not date_value:
        return
    data["g62_date_raw"] = data["g62_date_raw"] or date_value
    if not data.get(header_date_field):
        data[header_date_field] = date_value


def _party_from_n1(segment: list[str]) -> tuple[str, str | None, str | None, str | None, str | None]:
    entity = (_element(segment, 1) or "").upper()
    name = _element(segment, 2)
    qualifier = (_element(segment, 3) or "").upper() or None
    identifier = _element(segment, 4)
    # A GLN is stored only when N103 says UL. Qualifier 92 is an assigned
    # id, so it stays on the identifier field and the GLN stays empty.
    gln = identifier if qualifier == "UL" else None
    return entity, name, qualifier, identifier, gln


def _assign_identified_party(
    data: dict[str, Any],
    prefix: str,
    name: str | None,
    qualifier: str | None,
    identifier: str | None,
    gln: str | None,
) -> None:
    _keep_first(data, f"{prefix}_name", name)
    _keep_first(data, f"{prefix}_id", identifier)
    _keep_first(data, f"{prefix}_id_qualifier", qualifier)
    _keep_first(data, f"{prefix}_gln", gln)


def _fill_reference_if_blank(data: dict[str, Any]) -> None:
    if data.get("reference_document_number"):
        return
    refs = data.get("reference_numbers") or {}
    for key in ("BM", "SI", "PO", "PK", "CN"):
        if refs.get(key):
            data["reference_document_number"] = refs[key]
            return


def _envelope_defaults() -> dict[str, Any]:
    return {
        "sender_id": None,
        "receiver_id": None,
        "isa_sender_id": None,
        "isa_receiver_id": None,
        "gs_sender_id": None,
        "gs_receiver_id": None,
        "isa13": None,
        "gs_control_number": None,
        "envelope_mismatch": False,
        "control_number": None,
    }


def _extract_944_fields(segments: list[list[str]]) -> dict[str, Any]:
    """Extract fields from X12 944 Warehouse Stock Transfer Receipt Advice.

    W17 is the receipt header. W0701 is quantity received. The warehouse
    (N1*WH) is the receiving location. The ship-from party is N1*SF when
    present, otherwise the depositor.
    """
    data: dict[str, Any] = {
        **_envelope_defaults(),
        "reporting_code": None,
        "receive_date_raw": None,
        "g62_date_raw": None,
        "g62_date_qualifier": None,
        "warehouse_receipt_number": None,
        "depositor_order_number": None,
        "shipment_id": None,
        "reference_document_number": None,
        "po_number": None,
        "bill_of_lading": None,
        "warehouse_name": None,
        "warehouse_id": None,
        "warehouse_id_qualifier": None,
        "warehouse_gln": None,
        "depositor_name": None,
        "depositor_id": None,
        "depositor_id_qualifier": None,
        "depositor_gln": None,
        "ship_from_name": None,
        "ship_from_gln": None,
        "ship_to_name": None,
        "ship_to_gln": None,
        "receiving_location_name": None,
        "receiving_location_gln": None,
        "reference_numbers": {},
        "line_items": [],
    }

    _apply_envelope_ids(data, segments)

    st = _first_segment(segments, "ST")
    if st and len(st) > 2:
        data["control_number"] = st[2]

    w17 = _first_segment(segments, "W17")
    if w17:
        data["reporting_code"] = _element(w17, 1)
        data["receive_date_raw"] = _element(w17, 2)
        data["warehouse_receipt_number"] = _element(w17, 3)
        data["depositor_order_number"] = _element(w17, 4)
        data["shipment_id"] = _element(w17, 5)

    # Header wins. N9 fills the reference only when W17 left it blank.
    data["reference_document_number"] = data["warehouse_receipt_number"] or data["shipment_id"]

    saw_ship_from = False
    for segment in segments:
        if not segment:
            continue
        seg_id = segment[0].upper()

        if seg_id == "N1":
            entity, name, qualifier, identifier, gln = _party_from_n1(segment)
            if entity in _FROM_ENTITY_CODES:
                saw_ship_from = True
                _keep_first(data, "ship_from_name", name)
                _keep_first(data, "ship_from_gln", gln)
            elif entity in _TO_ENTITY_CODES:
                _keep_first(data, "ship_to_name", name)
                _keep_first(data, "ship_to_gln", gln)
            elif entity == "WH":
                _assign_identified_party(data, "warehouse", name, qualifier, identifier, gln)
            elif entity == "DE":
                _assign_identified_party(data, "depositor", name, qualifier, identifier, gln)

        elif seg_id == "N9":
            _apply_n9(data, segment)

        elif seg_id == "G62":
            _note_g62(data, segment, "receive_date_raw")

        elif seg_id == "G69":
            text = _element(segment, 1)
            if text and data["line_items"]:
                data["line_items"][-1]["product_description"] = text

        elif seg_id == "W07":
            quantity = _safe_float(_element(segment, 1), fallback=0.0)
            line = {
                "quantity": quantity if isfinite(quantity) and quantity > 0 else None,
                "unit_of_measure": _element(segment, 2),
                "upc": _element(segment, 3),
                "gtin": None,
                "product_description": None,
                "lot_number": _element(segment, 8),
            }
            _apply_product_pairs(line, segment, _W07_PRODUCT_PAIRS)
            data["line_items"].append(line)

    if not saw_ship_from:
        data["ship_from_name"] = data["depositor_name"]
        data["ship_from_gln"] = data["depositor_gln"]
    if data["warehouse_name"] or data["warehouse_gln"]:
        data["receiving_location_name"] = data["warehouse_name"]
        data["receiving_location_gln"] = data["warehouse_gln"]
    else:
        data["receiving_location_name"] = data["ship_to_name"]
        data["receiving_location_gln"] = data["ship_to_gln"]
    _fill_reference_if_blank(data)
    return data


def _extract_945_fields(segments: list[list[str]]) -> dict[str, Any]:
    """Extract fields from X12 945 Warehouse Shipping Advice.

    W06 is the shipment header. W1203 is units shipped (the CTE quantity).
    W1202 is quantity ordered and is kept aside so it cannot replace shipped.
    Ship-from is N1*SF when present, otherwise the warehouse (N1*WH).
    """
    data: dict[str, Any] = {
        **_envelope_defaults(),
        "reporting_code": None,
        "ship_date_raw": None,
        "g62_date_raw": None,
        "g62_date_qualifier": None,
        "depositor_order_number": None,
        "shipment_id": None,
        "agent_shipment_id": None,
        "po_number": None,
        "reference_document_number": None,
        "bill_of_lading": None,
        "warehouse_name": None,
        "warehouse_id": None,
        "warehouse_id_qualifier": None,
        "warehouse_gln": None,
        "depositor_name": None,
        "depositor_id": None,
        "depositor_id_qualifier": None,
        "depositor_gln": None,
        "ship_from_name": None,
        "ship_from_gln": None,
        "ship_to_name": None,
        "ship_to_gln": None,
        "reference_numbers": {},
        "line_items": [],
    }

    _apply_envelope_ids(data, segments)

    st = _first_segment(segments, "ST")
    if st and len(st) > 2:
        data["control_number"] = st[2]

    w06 = _first_segment(segments, "W06")
    if w06:
        data["reporting_code"] = _element(w06, 1)
        data["depositor_order_number"] = _element(w06, 2)
        data["ship_date_raw"] = _element(w06, 3)
        data["shipment_id"] = _element(w06, 4)
        data["agent_shipment_id"] = _element(w06, 5)
        data["po_number"] = _element(w06, 6)

    data["reference_document_number"] = data["shipment_id"] or data["depositor_order_number"]

    saw_ship_from = False
    for segment in segments:
        if not segment:
            continue
        seg_id = segment[0].upper()

        if seg_id == "N1":
            entity, name, qualifier, identifier, gln = _party_from_n1(segment)
            if entity in _FROM_ENTITY_CODES:
                saw_ship_from = True
                _keep_first(data, "ship_from_name", name)
                _keep_first(data, "ship_from_gln", gln)
            elif entity in _TO_ENTITY_CODES:
                _keep_first(data, "ship_to_name", name)
                _keep_first(data, "ship_to_gln", gln)
            elif entity == "WH":
                _assign_identified_party(data, "warehouse", name, qualifier, identifier, gln)
            elif entity == "DE":
                _assign_identified_party(data, "depositor", name, qualifier, identifier, gln)

        elif seg_id == "N9":
            _apply_n9(data, segment)

        elif seg_id == "G62":
            _note_g62(data, segment, "ship_date_raw")

        elif seg_id == "G69":
            text = _element(segment, 1)
            if text and data["line_items"]:
                data["line_items"][-1]["product_description"] = text

        elif seg_id == "W12":
            ordered_raw = _element(segment, 2)
            try:
                ordered = float(ordered_raw) if ordered_raw is not None else None
            except ValueError:
                ordered = None
            quantity = _safe_float(_element(segment, 3), fallback=0.0)
            line = {
                "quantity": quantity if isfinite(quantity) and quantity > 0 else None,
                "quantity_ordered": ordered if ordered is not None and isfinite(ordered) else None,
                "unit_of_measure": _element(segment, 5),
                "upc": _element(segment, 6),
                "gtin": None,
                "product_description": None,
                "lot_number": _element(segment, 9),
            }
            _apply_product_pairs(line, segment, _W12_PRODUCT_PAIRS)
            data["line_items"].append(line)

    if not saw_ship_from:
        data["ship_from_name"] = data["warehouse_name"]
        data["ship_from_gln"] = data["warehouse_gln"]
    _fill_reference_if_blank(data)
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
    elif transaction_set == "944":
        return _extract_944_fields(segments)
    elif transaction_set == "945":
        return _extract_945_fields(segments)
    return {}
