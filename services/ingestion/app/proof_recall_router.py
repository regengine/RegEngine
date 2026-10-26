"""Public recall-drill endpoint.

Endpoint: ``POST /api/v1/proof/recall-drill``

This is a public, tenantless, unauthenticated surface (rate limit: 5
requests per minute per IP via the shared slowapi ``limiter``). It MUST
NEVER read tenant data: this module imports no ``shared.database``,
``CTEPersistence`` or other tenant-scoped client.

Because it cannot read tenant data, it has no real recall to trace. It
previously returned a frozen synthetic drill (an invented lot, invented
facilities, invented step durations and a pre-generated sample CSV).
That was fake data presented as a proof, so it was removed. The endpoint
now returns an honest empty result: no steps, no lot code, no trace time
and no CSV, with ``data_available: false``. The only populated value is
the FDA 24-hour records-production window from 21 CFR 1.1455(c)(3),
which is a regulatory constant, not data.

Returned JSON shape::

    {
      "data_available": false,
      "steps": [],
      "time_to_trace_seconds": null,
      "output_csv_url": null,
      "lot_code": null,
      "fda_24h_mandate_seconds": 86400,
      "message": str,
      "timestamp": str
    }
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from shared.rate_limit import limiter

logger = logging.getLogger("proof-recall")

router = APIRouter(prefix="/api/v1/proof", tags=["Public Proof"])

# 21 CFR 1.1455(c)(3): records must be provided to FDA within 24 hours.
FDA_24H_MANDATE_SECONDS = 86400

NO_DATA_MESSAGE = (
    "No recall drill data is available on this public endpoint. "
    "Run a recall trace against your own records after signing in."
)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class DrillStep(BaseModel):
    name: str
    duration_ms: int = Field(..., ge=0)
    status: Literal["ok", "warning", "error"]
    detail: Optional[str] = None


class RecallDrillResponse(BaseModel):
    data_available: bool = False
    steps: list[DrillStep] = Field(default_factory=list)
    time_to_trace_seconds: Optional[float] = None
    output_csv_url: Optional[str] = None
    lot_code: Optional[str] = None
    fda_24h_mandate_seconds: int = FDA_24H_MANDATE_SECONDS
    message: str = NO_DATA_MESSAGE
    timestamp: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_ip(client_host: Optional[str]) -> str:
    """Anonymize the caller IP for log correlation (sha256(ip)[:16])."""
    if not client_host:
        return "unknown"
    return hashlib.sha256(client_host.encode("utf-8")).hexdigest()[:16]


def _build_response() -> RecallDrillResponse:
    """Build the honest empty response. No I/O, no tenant lookups."""
    return RecallDrillResponse(timestamp=_now_iso())


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------
@router.post(
    "/recall-drill",
    response_model=RecallDrillResponse,
    summary="Public recall drill: returns an honest empty result (no tenant data is read)",
)
@limiter.limit("5/minute")
async def run_recall_drill(request: Request) -> RecallDrillResponse:
    """Return an honest empty recall-drill result.

    Takes no body and reads no tenant data, so there is nothing real to
    trace: ``steps`` is empty, ``lot_code``, ``time_to_trace_seconds``
    and ``output_csv_url`` are null, and ``data_available`` is false.
    """
    ip_hash = _hash_ip(request.client.host if request.client else None)
    response = _build_response()
    logger.info(
        "proof_recall_drill_call",
        extra={"ip_hash": ip_hash, "data_available": response.data_available},
    )
    return response
