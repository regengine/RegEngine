"""
PCOS Router Package — Production Compliance OS

Barrel module that aggregates all PCOS sub-routers into a single router.
The monolithic pcos_routes.py is being decomposed into domain-specific modules.

Import pattern (backward-compatible):
    from app.pcos import router
    # or via the shim:
    from app.pcos_routes import router
"""

from fastapi import APIRouter

from .governance import router as governance_router
from .authority import router as authority_router
from .dashboard import router as dashboard_router
from .gate import router as gate_router
from .entities import router as entities_router
from .evidence import router as evidence_router
from .budget import router as budget_router
from .compliance import router as compliance_router

# Unified router — all sub-routers merge here
router = APIRouter(prefix="/pcos", tags=["Production Compliance OS"])

router.include_router(governance_router)
router.include_router(authority_router)
router.include_router(dashboard_router)
router.include_router(gate_router)
router.include_router(entities_router)
router.include_router(evidence_router)
router.include_router(budget_router)
router.include_router(compliance_router)
