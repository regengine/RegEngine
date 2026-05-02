from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from ..webhook_models import IngestResponse


class EDIIngestResponse(BaseModel):
    """Response for EDI ingestion requests."""

    status: str = "accepted"
    parser_name: str = "edi_parser"
    document_type: str = "X12_856"
    sender_tenant_id: str
    partner_id: Optional[str] = None
    traceability_lot_code: str
    extracted: dict[str, Any] = Field(default_factory=dict)
    # Optional: populated only when the document was persisted into the
    # canonical ingest stream. A rejected document (#1174 advisory mode)
    # leaves this None and surfaces ``rejection`` instead.
    ingestion_result: Optional[IngestResponse] = None
    # Populated only for FSMA-invalid documents accepted in advisory
    # mode. Callers must treat ``rejection`` as mutually exclusive with
    # ``ingestion_result`` — an EDI document either lives in the
    # canonical stream OR in the rejection log, never both (#1174).
    rejection: Optional[dict[str, Any]] = None
