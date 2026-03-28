"""
FDA Export Response Models.

Pydantic models for JSON-returning endpoints in fda_export_router.py.
StreamingResponse endpoints (CSV/ZIP) use OpenAPI `responses` metadata
in the route decorator instead of response_model.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# /export/history
# ---------------------------------------------------------------------------


class ExportHistoryItem(BaseModel):
    """Single entry in the FDA export audit log."""

    id: str
    export_type: Optional[str] = None
    query_tlc: Optional[str] = None
    query_start_date: Optional[str] = None
    query_end_date: Optional[str] = None
    record_count: int
    export_hash: str
    generated_by: Optional[str] = None
    generated_at: Optional[str] = None


class ExportHistoryResponse(BaseModel):
    """Response for GET /api/v1/fda/export/history."""

    tenant_id: str
    exports: List[ExportHistoryItem]
    total: int


# ---------------------------------------------------------------------------
# /export/verify
# ---------------------------------------------------------------------------


class ExportVerifyResponse(BaseModel):
    """Response for POST /api/v1/fda/export/verify."""

    export_id: str
    original_hash: str
    regenerated_hash: str
    hashes_match: bool
    original_record_count: int
    current_record_count: int
    data_integrity: str = Field(
        description="VERIFIED if hashes match, MISMATCH_DETECTED otherwise"
    )
    original_generated_at: Optional[str] = None
    verified_at: str
