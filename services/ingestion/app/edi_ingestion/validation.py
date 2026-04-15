from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from .utils import _valid_gln_or_none

logger = logging.getLogger("edi-ingestion")


def _validate_edi_as_fsma_event(
    extracted: dict[str, Any],
    transaction_set: str,
    tlc: str,
    tenant_id: str | None = None,
) -> dict | None:
    """Validate EDI-extracted data against the FSMAEvent Pydantic model.

    Returns the validated model dict on success, or None on failure.
    """
    try:
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

        event_time = datetime.now(timezone.utc).isoformat()
        for date_field in ("ship_date_raw", "po_date_raw", "invoice_date_raw", "receive_date_raw"):
            raw_date = extracted.get(date_field)
            if raw_date:
                clean = re.sub(r"\D", "", raw_date)
                if len(clean) == 8:
                    try:
                        dt = datetime(
                            year=int(clean[:4]), month=int(clean[4:6]), day=int(clean[6:8]),
                            tzinfo=timezone.utc,
                        )
                        event_time = dt.isoformat()
                        break
                    except ValueError:
                        pass

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
    except (ValidationError, ImportError) as exc:
        logger.warning("edi_fsma_validation_failed set=%s error=%s", transaction_set, str(exc))
        return None
