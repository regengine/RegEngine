from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from app.webhook_models import IngestResponse


class EDIIngestResponse(BaseModel):
    """Response for EDI ingestion requests."""

    status: str = "accepted"
    parser_name: str = "edi_parser"
    document_type: str = "X12_856"
    sender_tenant_id: str
    partner_id: Optional[str] = None
    traceability_lot_code: str
    extracted: dict[str, Any] = Field(default_factory=dict)
    ingestion_result: IngestResponse
