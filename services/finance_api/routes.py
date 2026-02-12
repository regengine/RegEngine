"""
Auto-generated FastAPI routes for finance vertical.
DO NOT MODIFY MANUALLY - regenerate via: regengine compile vertical finance
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
import logging

from .models import (
    DecisionRequest,
    DecisionResponse,
    SnapshotResponse,
    ExportRequest
)
from .service import FinanceDecisionService

logger = logging.getLogger(__name__)

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
    service: FinanceDecisionService = Depends(get_service)
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
        logger.error(f"Decision recording failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Decision recording failed: {str(e)}"
        )


@router.get("/decision/{decision_id}", response_model=Dict[str, Any])
async def get_decision(
    decision_id: str,
    service: FinanceDecisionService = Depends(get_service)
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
async def get_snapshot(service: FinanceDecisionService = Depends(get_service)):
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
    from .snapshot_service import FinanceSnapshotService
    
    logger.info("Computing compliance snapshot")
    
    # Get all decisions and evaluations
    decisions = list(service.decisions.values())
    models = []  # Would fetch from model registry
    
    # Get obligation evaluations (simplified - would query from ROE)
    obligation_evaluations = []
    
    # Compute snapshot using analytics engines
    snapshot_service = FinanceSnapshotService()
    snapshot = snapshot_service.compute_snapshot(
        decisions=decisions,
        models=models,
        obligation_evaluations=obligation_evaluations
    )
    
    return snapshot



@router.get("/stats")
async def get_stats(service: FinanceDecisionService = Depends(get_service)):
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
