from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from ..webhook_models import IngestResponse

EDIIngestStatus = Literal["accepted", "partial", "rejected"]


def ingest_status(result: IngestResponse) -> EDIIngestStatus:
    """Name the document outcome from what ``ingest_events`` stored."""
    if result.accepted == 0:
        return "rejected"
    return "partial" if result.rejected else "accepted"


class EDIIngestResponse(BaseModel):
    """Response for EDI ingestion requests.

    ``status`` is the document outcome. All three values arrive with HTTP 201:

    - ``accepted``: every event was stored.
    - ``partial``: some events were stored. ``ingestion_result.events`` shows
      which, and carries the errors for the rest.
    - ``rejected``: nothing was stored. ``ingestion_result`` carries the
      per-event errors, or ``rejection`` when advisory mode (#1174) stopped
      the document before ingest.

    It has no default, so a new return path has to state its outcome.
    """

    status: EDIIngestStatus
    parser_name: str = "edi_parser"
    document_type: str = "X12_856"
    sender_tenant_id: str
    partner_id: Optional[str] = None
    traceability_lot_code: str
    extracted: dict[str, Any] = Field(default_factory=dict)
    # Optional: populated when the document reached ``ingest_events``, even
    # if every event was rejected there. A document stopped before ingest
    # (#1174 advisory mode) leaves this None and surfaces ``rejection``.
    ingestion_result: Optional[IngestResponse] = None
    # Populated only for FSMA-invalid documents accepted in advisory
    # mode. Callers must treat ``rejection`` as mutually exclusive with
    # ``ingestion_result`` — an EDI document either lives in the
    # canonical stream OR in the rejection log, never both (#1174).
    rejection: Optional[dict[str, Any]] = None
