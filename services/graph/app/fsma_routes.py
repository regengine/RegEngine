"""
FSMA 204 Compliance API Routes.

Aggregates modular routers:
- Traceability (Forward/Backward/Timeline)
- Science (Mass Balance)
- Compliance (Exports, Gaps, Plans)
- Audit (Audit Trail, Drift)
- Identifiers (Validation)
- Metrics (Health, Prometheus)
"""

from fastapi import APIRouter

from .routers.fsma import (
    audit,
    compliance,
    identifiers,
    metrics,
    recall,
    science,
    traceability,
)

fsma_router = APIRouter(prefix="/v1/fsma", tags=["FSMA 204"])

# Include sub-routers
fsma_router.include_router(traceability.router)
fsma_router.include_router(science.router)
fsma_router.include_router(compliance.router)
fsma_router.include_router(audit.router)
fsma_router.include_router(recall.router)
fsma_router.include_router(identifiers.router)
fsma_router.include_router(metrics.router)
