from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from .utils import _parse_edi_date_digits, _valid_gln_or_none

logger = logging.getLogger("edi-ingestion")


class _WarehouseLineRequiredKDEs(BaseModel):
    """Lot and positive quantity required on each 944 or 945 line.

    The failure is a pydantic ValidationError so the document route can
    use the same strict and advisory rejection path as the other sets.
    """

    lot_number: str = Field(min_length=1)
    quantity: float = Field(gt=0)


def _validate_edi_as_fsma_event(
    extracted: dict[str, Any],
    transaction_set: str,
    tlc: str,
    tenant_id: str | None = None,
) -> dict:
    """Validate EDI-extracted data against the FSMAEvent Pydantic model.

    Returns the validated model dict on success. Raises
    ``pydantic.ValidationError`` on schema failure so the caller can
    decide between strict (#1174 — 422 and refuse to persist) and
    advisory (log and persist with status=failed). Previously this
    function swallowed ValidationError and returned ``None``, which
    forced every caller to treat ``None`` as "maybe-failed, maybe-
    unavailable" and masked schema errors in the audit trail.
    """
    from shared.schemas import _TLC_PRODUCTION_RE, FSMAEvent, FSMAEventType

    type_map = {
        "856": FSMAEventType.SHIPPING,
        "850": FSMAEventType.SHIPPING,
        "810": FSMAEventType.SHIPPING,
        "861": FSMAEventType.RECEIVING,
        "944": FSMAEventType.RECEIVING,
        "945": FSMAEventType.SHIPPING,
    }
    fsma_type = type_map.get(transaction_set, FSMAEventType.SHIPPING)

    if transaction_set in ("944", "945"):
        line = _WarehouseLineRequiredKDEs(
            lot_number=extracted.get("lot_number"),
            quantity=extracted.get("quantity"),
        )
        tlc = line.lot_number.strip()
        # A-2170: a whitespace-only lot strips empty. Reject before the
        # GTIN/UPC rebuild so we never emit a production-shaped "GTIN-"
        # TLC that FSMAEvent would accept, collapsing blank lots onto one id.
        if not tlc:
            _WarehouseLineRequiredKDEs(lot_number=tlc, quantity=line.quantity)
        # Pattern misses are advisory, so check explicitly to retain the
        # warehouse GTIN/UPC rebuild for both accepted and short lots.
        try:
            tlc = FSMAEvent.validate_tlc_format(tlc)
            rebuild = not _TLC_PRODUCTION_RE.fullmatch(tlc)
        except ValueError:
            rebuild = True
        if rebuild:
            for item_id, lengths in (
                (extracted.get("gtin"), (8, 12, 13, 14)),
                (extracted.get("upc"), (12, 13)),
            ):
                if isinstance(item_id, str) and item_id.isascii() and item_id.isdigit() and len(item_id) in lengths:
                    tlc = f"{item_id.zfill(14)}-{tlc}"
                    break
    elif transaction_set in ("856", "861"):
        # The line lot is the TLC verbatim. Do not prefix a GTIN (#1104).
        # A line with no lot keeps the caller-supplied form field.
        lot = extracted.get("lot_number")
        if isinstance(lot, str) and lot.strip():
            tlc = lot.strip()

    # Resolve location GLN from whichever field is available
    location_gln = (
        extracted.get("ship_from_gln")
        or extracted.get("seller_gln")
        or extracted.get("receiving_location_gln")
        or extracted.get("buyer_gln")
    )

    source_gln = extracted.get("ship_from_gln") or extracted.get("seller_gln")
    dest_gln = extracted.get("ship_to_gln") or extracted.get("buyer_gln") or extracted.get("receiving_location_gln")

    # #1167: prefer any parseable EDI date (CCYYMMDD or YYMMDD) before
    # falling back to ``now()``. Stale dates used to silently become
    # today's timestamp, inverting FSMA traceability ordering.
    event_time = datetime.now(timezone.utc).isoformat()
    for date_field in ("ship_date_raw", "po_date_raw", "invoice_date_raw", "receive_date_raw"):
        raw_date = extracted.get(date_field)
        if not raw_date:
            continue
        digits = re.sub(r"\D", "", raw_date)
        try:
            event_time = _parse_edi_date_digits(digits).isoformat()
            break
        except ValueError:
            continue

    doc_type_map = {
        "856": "EDI_856",
        "850": "EDI_850",
        "810": "EDI_810",
        "861": "EDI_861",
        "944": "EDI_944",
        "945": "EDI_945",
    }

    fsma_event = FSMAEvent(
        event_type=fsma_type,
        tlc=tlc,
        product_description=extracted.get("product_description") or f"EDI {transaction_set} Item",
        quantity=extracted.get("quantity"),
        unit_of_measure=extracted.get("unit_of_measure"),
        location_gln=_valid_gln_or_none(location_gln),
        event_time=event_time,
        source_gln=_valid_gln_or_none(source_gln),
        destination_gln=_valid_gln_or_none(dest_gln),
        reference_document_type=doc_type_map.get(transaction_set, f"EDI_{transaction_set}"),
        reference_document_number=extracted.get("reference_document_number"),
        tenant_id=tenant_id,
    )
    return fsma_event.model_dump()
