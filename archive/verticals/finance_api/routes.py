"""
FastAPI routes for finance vertical.

Originally auto-generated via: regengine compile vertical finance
SEC-FIN-001/002 REMEDIATION: Manually patched to add authentication
and error handling hardening. Compiler template should incorporate
these patterns before next regeneration.
"""

import sys
from pathlib import Path

import structlog
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any

# Ensure shared modules are importable
_SERVICES_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SERVICES_DIR))

from shared.auth import require_api_key

from .models import (
    DecisionRequest,
    DecisionResponse,
    SnapshotResponse,
    ExportRequest
)
from .service import FinanceDecisionService

logger = structlog.get_logger("finance_routes")

router = APIRouter(prefix="/v1/finance", tags=["finance"])

# Initialize service (singleton pattern)
_service_instance = None


def get_service() -> FinanceDecisionService:
    """Get or create FinanceDecisionService singleton."""
    global _service_instance
    if _service_instance is None:
        _service_instance = FinanceDecisionService(verticals_dir="./verticals")
    return _service_instance


@router.post("/decision/record", response_model=DecisionResponse)
async def record_decision(
    request: DecisionRequest,
    service: FinanceDecisionService = Depends(get_service),
    _api_key=Depends(require_api_key),
):
    """
    Record a finance decision with evidence.
    
    **Workflow**:
    1. Validate evidence against evidence_contract
    2. Evaluate against regulatory obligations (ROE)
    3. Create cryptographic evidence envelope (Evidence V3)
    4. Persist to graph + DB
    
    **Decision Types**: credit_approval, credit_denial, limit_adjustment, fraud_flag, account_closure
    
    **Returns**:
    - Evaluation ID
    - Obligation coverage percentage
    - Risk level (low/medium/high/critical)
    """
    try:
        response = service.record_decision(request)
        return response
        
    except Exception as e:
        logger.error("decision_recording_failed", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Decision recording failed. Check server logs for details."
        )


@router.get("/decision/{decision_id}", response_model=Dict[str, Any])
async def get_decision(
    decision_id: str,
    service: FinanceDecisionService = Depends(get_service),
    _api_key=Depends(require_api_key),
):
    """Retrieve a decision record by ID."""
    decision = service.get_decision(decision_id)
    
    if decision is None:
        raise HTTPException(
            status_code=404,
            detail=f"Decision {decision_id} not found"
        )
    
    return decision


@router.get("/snapshot", response_model=SnapshotResponse)
async def get_snapshot(
    service: FinanceDecisionService = Depends(get_service),
    _api_key=Depends(require_api_key),
):
    """
    Get current compliance snapshot for finance vertical.
    
    **Computes**:
    - **Bias score** (30%): DIR, 80% rule compliance across protected classes
    - **Drift score** (20%): PSI, KL/JS divergence for model features
    - **Documentation score** (25%): Model cards, decision logs completeness
    - **Regulatory mapping score** (25%): Obligation coverage and compliance
    
    **Risk Levels**:
    - low: >= 90% compliance
    - medium: 70-89% compliance
    - high: 50-69% compliance
    - critical: < 50% compliance
    """
    from .snapshot_adapter import FinanceSnapshotAdapter
    
    logger.info("computing_compliance_snapshot")
    
    # Use Adapter to fetch data from Graph/DB and compute snapshot
    # This addresses Issue #67 (Unimplemented Graph Queries)
    if service.graph_store:
        adapter = FinanceSnapshotAdapter(
            graph_client=service.graph_store.driver,
            db_client=service.db_engine
        )
        snapshot_data = adapter.compute_snapshot()
        
        # Convert dict to SnapshotResponse model
        snapshot = SnapshotResponse(**snapshot_data)
    else:
        logger.warning("graph_store_not_available", fallback="empty_snapshot")
        # Fallback to empty/mock if graph is down
        from .snapshot_service import FinanceSnapshotService
        snapshot_service = FinanceSnapshotService()
        snapshot = snapshot_service.compute_snapshot(
            decisions=[], models=[], obligation_evaluations=[]
        )
        
    return snapshot



@router.get("/stats")
async def get_stats(
    service: FinanceDecisionService = Depends(get_service),
    _api_key=Depends(require_api_key),
):
    """Get Finance API statistics."""
    chain_stats = service.get_chain_stats()
    
    return {
        "service": "finance_api",
        "decisions_recorded": chain_stats["total_decisions"],
        "evidence_envelopes": chain_stats["total_envelopes"],
        "chain_status": "active" if chain_stats["latest_envelope_hash"] else "empty"
    }


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "finance_api"
    }
