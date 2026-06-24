"""Public recall-drill endpoint.

Why this belongs in the FSMA pipeline (production-surface promotion rule
per ``PRODUCTION_SURFACE.md``):

The core production contract is::

    ingest -> canonicalize -> validate -> persist evidence -> export

This router adds a public, tenantless surface that demonstrates the
*recall-response* capability built on top of the export stage. It is
the FSMA pipeline's public proof surface for recall capability: a
prospect, regulator, or trade partner can run a deterministic recall
drill against a frozen synthetic dataset and observe the wall-clock
trace time vs. the FDA 24-hour mandate, without an account, without
tenant context, and without reading any tenant data.

Endpoint: ``POST /api/v1/proof/recall-drill``

- No auth (public). Rate limit: 5 requests per minute per IP via the
  shared slowapi ``limiter`` (``shared.rate_limit``).
- Operates *only* against a frozen synthetic dataset baked into this
  module. The endpoint MUST NEVER read real tenant data: static
  analysis of this module should show zero imports of
  ``shared.database``, ``CTEPersistence``, or any tenant-scoped
  client.
- Output is deterministic — every call returns the same step list,
  ``time_to_trace_seconds`` (sum of step durations), ``lot_code``,
  and ``output_csv_url``.
- The pre-generated recall CSV referenced by ``output_csv_url`` lives
  in the frontend's public assets (``/samples/sample_recall_drill.csv``)
  and was produced from the synthetic 7-CTE dataset.

Returned JSON shape::

    {
      "steps": [
        {"name": str, "duration_ms": int,
         "status": "ok"|"warning"|"error", "detail": str?},
        ...
      ],
      "time_to_trace_seconds": float,
      "output_csv_url": str,
      "lot_code": str,
      "fda_24h_mandate_seconds": 86400
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


# ---------------------------------------------------------------------------
# Frozen synthetic drill -- deterministic by construction
# ---------------------------------------------------------------------------
# This corresponds to the public CSV at
# ``frontend/public/samples/sample_recall_drill.csv`` -- a known-contaminated
# romaine lot harvested at Sunny Valley Farms, traced forward through the
# 7 CTEs (harvesting, cooling, initial packing, shipping, receiving,
# transformation, shipping) into Metro Foods, Valley Wholesale, and
# SuperMart #42.
FROZEN_LOT_CODE = "SV-20240115-001"
OUTPUT_CSV_URL = "/samples/sample_recall_drill.csv"
FDA_24H_MANDATE_SECONDS = 86400

# Steps mirror the synthetic frontend script so a UI consuming this
# endpoint produces the same per-step animation. Durations sum to
# 7.0 seconds — well inside the 24h FDA mandate.
_FROZEN_STEPS: tuple[dict, ...] = (
    {
        "name": "Identifying source lot",
        "duration_ms": 1200,
        "status": "ok",
        "detail": (
            "Loaded contaminated lot SV-20240115-001 (Romaine Lettuce, "
            "500 cases) from Sunny Valley Farms (GLN 1234567890128)."
        ),
    },
    {
        "name": "Tracing forward through 7 CTEs",
        "duration_ms": 2400,
        "status": "ok",
        "detail": (
            "Walked CTE-1 HARVESTING -> CTE-2 COOLING -> CTE-3 "
            "INITIAL_PACKING -> CTE-4 SHIPPING -> CTE-5 RECEIVING -> "
            "CTE-6 TRANSFORMATION -> CTE-7 SHIPPING. Resolved 2 child "
            "lots (FC-20240116-A, FC-20240116-B) at the transformation "
            "node."
        ),
    },
    {
        "name": "Walking downstream graph edges",
        "duration_ms": 1800,
        "status": "ok",
        "detail": (
            "Visited 11 events across 5 facilities. Reached 3 "
            "downstream receivers: Metro Foods, Valley Wholesale, "
            "SuperMart #42."
        ),
    },
    {
        "name": "Generating FDA-oriented recall CSV",
        "duration_ms": 1600,
        "status": "ok",
        "detail": (
            "Wrote § 204.2(g) Key Data Elements for each downstream "
            "lot. Hash-anchored each record (SHA-256 chain integrity "
            "preserved)."
        ),
    },
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
    steps: list[DrillStep]
    time_to_trace_seconds: float
    output_csv_url: str
    lot_code: str
    fda_24h_mandate_seconds: int = FDA_24H_MANDATE_SECONDS
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
    """Build the deterministic drill response.

    Pure function of module constants — no I/O, no tenant lookups.
    Two calls return identical ``steps`` / ``time_to_trace_seconds``
    (only ``timestamp`` differs).
    """
    steps = [DrillStep(**s) for s in _FROZEN_STEPS]
    total_ms = sum(s.duration_ms for s in steps)
    return RecallDrillResponse(
        steps=steps,
        time_to_trace_seconds=round(total_ms / 1000.0, 3),
        output_csv_url=OUTPUT_CSV_URL,
        lot_code=FROZEN_LOT_CODE,
        fda_24h_mandate_seconds=FDA_24H_MANDATE_SECONDS,
        timestamp=_now_iso(),
    )


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------
@router.post(
    "/recall-drill",
    response_model=RecallDrillResponse,
    summary="Run a deterministic recall drill against a frozen synthetic dataset",
)
@limiter.limit("5/minute")
async def run_recall_drill(request: Request) -> RecallDrillResponse:
    """Run a public recall drill against the frozen synthetic dataset.

    Takes no body. Returns a deterministic step list plus the
    wall-clock ``time_to_trace_seconds`` for the synthetic drill, the
    FDA 24-hour response target for client-side comparison, and the
    URL of a pre-generated FDA-oriented recall CSV.

    This endpoint MUST NOT read any tenant data: it operates entirely
    against module-level constants derived from
    ``frontend/public/samples/sample_recall_drill.csv`` and the
    7-CTE ``sample_data/`` fixtures. No database, queue, or tenant
    store is touched.
    """
    ip_hash = _hash_ip(request.client.host if request.client else None)
    response = _build_response()
    logger.info(
        "proof_recall_drill_call",
        extra={
            "ip_hash": ip_hash,
            "lot_code": response.lot_code,
            "time_to_trace_seconds": response.time_to_trace_seconds,
        },
    )
    return response
