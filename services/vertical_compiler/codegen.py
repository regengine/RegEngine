"""
Code Generation Module
======================
Generates FastAPI routes and Pydantic models from vertical schemas.

Uses string formatting for clean, maintainable code generation.
"""

from pathlib import Path
from typing import List, Dict, Any


def generate_fastapi_routes(vertical_meta, obligations: List) -> str:
    """
    Generate FastAPI routes file.
    
    Generates:
    - POST /v1/{vertical}/decision/record
    - POST /v1/{vertical}/decision/replay
    - GET /v1/{vertical}/snapshot
    - GET /v1/{vertical}/export
    """
    vertical_name = vertical_meta.name
    decision_types = ", ".join(f'"{dt}"' for dt in vertical_meta.decision_types)
    
    code = f'''"""
Auto-generated FastAPI routes for {vertical_name} vertical.
DO NOT MODIFY MANUALLY - regenerate via: regengine compile vertical {vertical_name}
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging

from .models import (
    DecisionRequest,
    DecisionResponse,
    SnapshotResponse,
    ExportRequest
)

logger = logging.getLogger(__name__)

{evidence_contract_placeholder}

router = APIRouter(prefix="/v1/{vertical_name}", tags=["{vertical_name}"])


@router.post("/decision/record", response_model=DecisionResponse)
async def record_decision(request: DecisionRequest):
    """
    Record a {vertical_name} decision with evidence.
    
    Decision Types: {', '.join(vertical_meta.decision_types)}
    """
    logger.info(f"Recording {{request.decision_type}} decision")
    
    # Import services (will be defined in generated service files)
    from .snapshot_service import {vertical_name.capitalize()}SnapshotService
    from .graph_store import {vertical_name.capitalize()}GraphStore
    
    try:
        # Initialize services
        graph_store = {vertical_name.capitalize()}GraphStore()
        snapshot_service = {vertical_name.capitalize()}SnapshotService(graph_store)
        
        # Validate evidence against evidence_contract
        required_fields = EVIDENCE_CONTRACT.get(request.decision_type, [])
        provided_fields = set(request.evidence.keys())
        missing_fields = set(required_fields) - provided_fields
        
        if missing_fields:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required evidence fields: {{missing_fields}}"
            )
        
        # Record decision
        decision_id = await graph_store.create_decision(
            decision_type=request.decision_type,
            evidence=request.evidence,
            metadata=request.metadata
        )
        
        # Evaluate against regulatory obligations
        obligation_results = await snapshot_service.evaluate_decision_obligations(
            decision_id=decision_id,
            decision_type=request.decision_type,
            evidence=request.evidence
        )
        
        # Create evidence envelope
        envelope_id = await graph_store.create_evidence_envelope(
            decision_id=decision_id,
            evidence=request.evidence
        )
        
        logger.info(f"Decision recorded: {{decision_id}}, envelope: {{envelope_id}}, obligations met: {{sum(1 for r in obligation_results if r['met'])}}/{{len(obligation_results)}}")
        
        return DecisionResponse(
            decision_id=decision_id,
            status="recorded",
           timestamp=datetime.utcnow().isoformat(),
            envelope_id=envelope_id,
            obligations_evaluated=len(obligation_results),
            obligations_met=sum(1 for r in obligation_results if r['met'])
        )
    except Exception as e:
        logger.error(f"Failed to record decision: {{e}}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/snapshot", response_model=SnapshotResponse)
async def get_snapshot():
    """
    Get current compliance snapshot for {vertical_name} vertical.
    
    Computes:
    - Bias score
    - Drift score
    - Documentation score
    - Regulatory mapping score
    - Overall compliance score
    """
    logger.info("Computing compliance snapshot")
    
    # Import snapshot adapter
    from .snapshot_adapter import {vertical_name.capitalize()}SnapshotAdapter
    from .graph_store import get_graph_client
    from .db import get_db_client
    
    try:
        # Initialize adapter with graph and DB clients
        graph = get_graph_client()
        db = get_db_client()
        adapter = {vertical_name.capitalize()}SnapshotAdapter(graph, db)
        
        # Compute snapshot
        snapshot = adapter.compute_snapshot()
        
        return SnapshotResponse(**snapshot)
    except Exception as e:
        logger.error(f"Failed to compute snapshot: {{e}}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {{
        "status": "healthy",
        "service": "{vertical_name}_api"
    }}
'''
    
    return code


def generate_pydantic_models(vertical_meta, obligations: List) -> str:
    """
    Generate Pydantic models file.
    
    Generates:
    - DecisionRequest
    - DecisionResponse
    - SnapshotResponse
    - ExportRequest
    """
    vertical_name = vertical_meta.name
    decision_types = ", ".join(f'"{dt}"' for dt in vertical_meta.decision_types)
    
    code = f'''"""
Auto-generated Pydantic models for {vertical_name} vertical.
DO NOT MODIFY MANUALLY - regenerate via: regengine compile vertical {vertical_name}
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum


class DecisionType(str, Enum):
    """Decision types for {vertical_name} vertical."""
    {chr(10).join(f'    {dt.upper()} = "{dt}"' for dt in vertical_meta.decision_types)}


class DecisionRequest(BaseModel):
    """Request to record a decision."""
    decision_id: str
    decision_type: DecisionType
    evidence: Dict[str, Any] = Field(..., description="Evidence payload")
    metadata: Optional[Dict[str, Any]] = None


class DecisionResponse(BaseModel):
    """Response from decision recording."""
    decision_id: str
    status: str
    timestamp: str
    evaluation_id: Optional[str] = None
    coverage_percent: Optional[float] = None
    risk_level: Optional[str] = None


class SnapshotResponse(BaseModel):
    """Compliance snapshot response."""
    snapshot_id: str
    timestamp: str
    vertical: str = "{vertical_name}"
    bias_score: float = 0.0
    drift_score: float = 0.0
    documentation_score: float = 0.0
    regulatory_mapping_score: float = 0.0
    obligation_coverage_percent: float = 0.0
    total_compliance_score: float = 0.0
    risk_level: str = "unknown"
    num_open_violations: int = 0


class ExportRequest(BaseModel):
    """Request to export compliance data."""
    export_type: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    format: str = "json"
'''
    
    return code


def generate_test_scaffolds(vertical_meta, obligations: List, output_dir: Path) -> List[Path]:
    """
    Generate test scaffold files.
    
    Generates:
    - test_routes.py
    - test_models.py
    """
    vertical_name = vertical_meta.name
    generated_files = []
    
    # Generate test_routes.py
    routes_test = f'''"""
Auto-generated route tests for {vertical_name} vertical.
"""

import pytest
from fastapi.testclient import TestClient


def test_record_decision():
    """Test decision recording endpoint."""
    # TODO: Implement test
    pass


def test_get_snapshot():
    """Test snapshot endpoint."""
    # TODO: Implement test
    pass


def test_health_check():
    """Test health check endpoint."""
    # TODO: Implement test
    pass
'''
    
    routes_test_file = output_dir / "test_routes.py"
    with open(routes_test_file, 'w') as f:
        f.write(routes_test)
    generated_files.append(routes_test_file)
    
    # Generate test_models.py
    models_test = f'''"""
Auto-generated model tests for {vertical_name} vertical.
"""

import pytest


def test_decision_type_enum():
    """Test DecisionType enum."""
    # TODO: Implement test
    pass


def test_decision_request_validation():
    """Test DecisionRequest validation."""
    # TODO: Implement test
    pass
'''
    
    models_test_file = output_dir / "test_models.py"
    with open(models_test_file, 'w') as f:
        f.write(models_test)
    generated_files.append(models_test_file)
    
    return generated_files
