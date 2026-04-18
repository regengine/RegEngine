from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from .utils import _parse_edi_date_digits, _valid_gln_or_none

logger = logging.getLogger("edi-ingestion")


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
    from shared.schemas import FSMAEvent, FSMAEventType

    type_map = {
        "856": FSMAEventType.SHIPPING,
        "850": FSMAEventType.SHIPPING,
        "810": FSMAEventType.SHIPPING,
        "861": FSMAEventType.RECEIVING,
    }
    fsma_type = type_map.get(transaction_set, FSMAEventType.SHIPPING)

    # Resolve location GLN from whichever field is available
    location_gln = (
        extracted.get("ship_from_gln")
        or extracted.get("seller_gln")
        or extracted.get("receiving_location_gln")
        or extracted.get("buyer_gln")
    )

    source_gln = extracted.get("ship_from_gln") or extracted.get("seller_gln")
    dest_gln = (
        extracted.get("ship_to_gln")
        or extracted.get("buyer_gln")
        or extracted.get("receiving_location_gln")
    )

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
