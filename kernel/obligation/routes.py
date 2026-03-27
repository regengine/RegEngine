"""
Regulatory Obligation Engine - FastAPI Routes
==============================================
REST API endpoints for obligation evaluation.
"""

from fastapi import APIRouter, HTTPException, Depends
from pathlib import Path
import os
import logging

from shared.auth import APIKey, require_api_key
from .models import (
    ObligationEvaluationRequest,
    ObligationEvaluationResult,
    ObligationCoverageReport
)
from .engine import RegulatoryEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/obligations", tags=["obligations"])

# Initialize engine
VERTICALS_DIR = Path(os.getenv("REGENGINE_VERTICALS_DIR", "./verticals"))
engine = RegulatoryEngine(verticals_dir=VERTICALS_DIR)


@router.post("/evaluate", response_model=ObligationEvaluationResult)
async def evaluate_obligations(request: ObligationEvaluationRequest, api_key: APIKey = Depends(require_api_key)):
    """
    Evaluate a decision against regulatory obligations.
    
    **Workflow**:
    1. Load applicable obligations for decision type
    2. Check triggering conditions
    3. Verify required evidence present
    4. Compute coverage %
    5. Assign risk scores
    6. Persist evaluation to graph
    
    **Returns**:
    - Evaluation result with coverage metrics
    - List of obligation matches (met/violated)
    - Overall risk score and level
    """
    try:
        result = engine.evaluate_decision(
            decision_id=request.decision_id,
            decision_type=request.decision_type,
            decision_data=request.decision_data,
            vertical=request.vertical
        )
        
        return result
        
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Evaluation failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")


@router.get("/coverage/{vertical}", response_model=ObligationCoverageReport)
async def get_coverage_report(vertical: str, api_key: APIKey = Depends(require_api_key)):
    """
    Get aggregate obligation coverage report for a vertical.
    
    **Returns**:
    - Average coverage %
    - Violation statistics by domain and regulator
    - Risk level distribution
    """
    try:
        report = engine.get_coverage_report(vertical=vertical)
        return report
    except Exception as e:
        logger.error(f"Coverage report failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Coverage report failed: {str(e)}")


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "regulatory_engine",
        "verticals_loaded": list(engine.evaluators.keys())
    }
