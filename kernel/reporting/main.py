#!/usr/bin/env python3
"""
RegEngine Compliance API Service

REST API for multi-industry compliance checklist validation.
Returns yes/no pass/fail status with line-item checklists.
"""

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from enum import Enum

from checklist_engine import (
    ComplianceChecklistEngine,
    ChecklistResult,
    ValidationStatus,
)
from fsma_engine import FSMA204ComplianceEngine
from drift_engine import DriftDetectionEngine, ComplianceHealth
from app.models import (
    ChecklistListResponse,
    ValidationRequest,
    ValidationResponse,
    ValidationItemResponse,
    FSMAAssessmentRequest,
    FSMAAssessmentResponse,
    DimensionScoreModel,
    TraceabilityPlanModel,
    KDECaptureModel,
    RecordkeepingModel,
    TechnologyModel,
    AnalysisSummary
)

from app.analysis import AnalysisEngine

# Import shared authentication
import sys
from pathlib import Path

# Centralised path resolution
_srv = str(Path(__file__).resolve().parent.parent)
if _srv not in sys.path:
    sys.path.insert(0, _srv)
from shared.paths import ensure_shared_importable
ensure_shared_importable()

from shared.auth import require_api_key, APIKey
from shared.middleware import TenantContextMiddleware, RequestIDMiddleware, get_current_tenant_id
from shared.tenant_rate_limiting import TenantRateLimitMiddleware
from shared.health import (
    HealthChecker,
    create_neo4j_check,
)


# CORS configuration
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.service_name,
    description="Multi-industry compliance checklist validation",
    version=settings.service_version,
)

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.add_middleware(RequestIDMiddleware)
app.add_middleware(TenantContextMiddleware)
app.add_middleware(TenantRateLimitMiddleware, default_rpm=100)

@app.middleware("http")
async def add_compliance_header(request, call_next):
    response = await call_next(request)
    response.headers["X-FSMA-204-Traceability"] = "true"
    return response

import structlog
_compliance_logger = structlog.get_logger("compliance-service")

@app.on_event("startup")
async def startup():
    _compliance_logger.info("compliance_service_started", version=settings.service_version)

@app.on_event("shutdown")
async def shutdown():
    _compliance_logger.info("compliance_service_stopped")

# Global exception handlers (Sprint 18)
from shared.error_handling import install_exception_handlers
install_exception_handlers(app)

# Initialize checklist engine with path relative to project root
# Initialize checklist engine with path relative to this file
_PLUGINS_DIR = Path(__file__).parent / "plugins"
engine = ComplianceChecklistEngine(plugin_directory=str(_PLUGINS_DIR))
fsma_engine = FSMA204ComplianceEngine()
drift_engine = DriftDetectionEngine()
analysis_engine = AnalysisEngine()


# ============================================================================
# Request/Response Models
# ============================================================================
# Models moved to app/models.py to reduce file size and allow reuse
# and imported above.


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """Deep health check endpoint with dependency verification."""
    
    checker = HealthChecker(service_name="compliance-api", version="1.0.0")
    
    # Add Neo4j check (optional - compliance may work without graph)
    # Add Neo4j check (optional - compliance may work without graph)
    if settings.neo4j_uri:
        checker.add_check("neo4j", create_neo4j_check(
            settings.neo4j_uri, 
            settings.neo4j_user, 
            settings.neo4j_password
        ))
    
    result = await checker.check_all(timeout=3.0)
    
    # Add service-specific info
    response = result.to_dict()
    response["checklists_loaded"] = len(engine.checklists)
    
    from fastapi.responses import JSONResponse
    status_code = 200 if result.status.value == "healthy" else 503
    return JSONResponse(content=response, status_code=status_code)


@app.get("/checklists", response_model=ChecklistListResponse)
def list_checklists(
    industry: Optional[str] = None,
    api_key: APIKey = Depends(require_api_key),
):
    """
    List all available compliance checklists

    - **industry**: Optional filter by industry (e.g., "finance", "healthcare")

    Returns list of checklists with metadata (ID, name, industry, jurisdiction)
    """
    checklists = engine.list_checklists(industry=industry)
    return ChecklistListResponse(checklists=checklists, total=len(checklists))


@app.get("/checklists/{checklist_id}")
def get_checklist(
    checklist_id: str,
    api_key: APIKey = Depends(require_api_key),
):
    """
    Get full details of a specific compliance checklist

    - **checklist_id**: Checklist identifier (e.g., "hipaa_compliance", "capital_requirements")

    Returns full checklist definition including all items and validation rules
    """
    checklist = engine.get_checklist(checklist_id)
    if not checklist:
        raise HTTPException(status_code=404, detail=f"Checklist not found: {checklist_id}")
    return checklist


@app.post("/validate", response_model=ValidationResponse)
def validate_compliance(
    request: ValidationRequest,
    api_key: APIKey = Depends(require_api_key),
):
    """
    Validate customer configuration against a compliance checklist

    **Returns yes/no pass/fail status with line-item results**

    Request body:
    ```json
    {
      "checklist_id": "hipaa_compliance",
      "customer_config": {
        "hipaa_001": true,
        "hipaa_002": true,
        "hipaa_003": false
      }
    }
    ```

    Response:
    ```json
    {
      "overall_status": "FAIL",
      "pass_rate": 0.67,
      "items": [
        {
          "requirement_id": "hipaa_001",
          "requirement": "Encrypt PHI at rest",
          "status": "PASS",
          "evidence": "Requirement met"
        },
        {
          "requirement_id": "hipaa_003",
          "requirement": "Role-Based Access Control",
          "status": "FAIL",
          "evidence": "Requirement not met",
          "remediation": "Implement RBAC system..."
        }
      ],
      "next_steps": [
        "Address failed requirements before launching",
        "→ Implement RBAC for PHI access"
      ]
    }
    ```
    """
    try:
        result = engine.validate_checklist(
            checklist_id=request.checklist_id,
            customer_config=request.customer_config
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Convert to response model
    return ValidationResponse(
        checklist_id=result.checklist_id,
        checklist_name=result.checklist_name,
        industry=result.industry,
        jurisdiction=result.jurisdiction,
        overall_status=result.overall_status.value,
        pass_rate=result.pass_rate,
        items=[
            ValidationItemResponse(
                requirement_id=item.requirement_id,
                requirement=item.requirement,
                regulation=item.regulation,
                status=item.status.value,
                evidence=item.evidence,
                remediation=item.remediation,
            )
            for item in result.items
        ],
        next_steps=result.next_steps,
    )


@app.get("/industries")
def list_industries(api_key: APIKey = Depends(require_api_key)):
    """
    List all supported industries

    Returns: List of industry names with checklist counts
    """
    industries = {}
    for checklist in engine.checklists.values():
        industry = checklist.get("industry", "unknown")
        industries[industry] = industries.get(industry, 0) + 1

    return {
        "industries": [
            {"name": name, "checklist_count": count}
            for name, count in sorted(industries.items())
        ],
        "total": len(industries),
    }


@app.post("/fsma-204/assess", response_model=FSMAAssessmentResponse)
def assess_fsma_readiness(
    request: FSMAAssessmentRequest,
    api_key: APIKey = Depends(require_api_key),
):
    """Run a FSMA 204 readiness assessment"""

    profile = request.dict()
    report = fsma_engine.evaluate(profile)
    payload = report.to_dict()
    metadata = payload.get("rule_metadata", {})

    return FSMAAssessmentResponse(
        rule_name=metadata.get("rule_name", "FSMA 204"),
        regulator=metadata.get("regulator", "FDA"),
        effective_date=metadata.get("effective_date"),
        facility_name=payload.get("facility_name", request.facility_name),
        overall_score=payload.get("overall_score", 0.0),
        risk_level=payload.get("risk_level", "UNKNOWN"),
        dimension_scores=[DimensionScoreModel(**item) for item in payload.get("dimension_scores", [])],
        remediation_actions=payload.get("remediation_actions", []),
    )


# ============================================================================
# FSMA 204 Audit Spreadsheet Endpoint
# ============================================================================

from fastapi.responses import StreamingResponse
from fsma_spreadsheet import generate_fda_spreadsheet


@app.get("/fsma/audit/spreadsheet")
def get_fsma_audit_spreadsheet(
    tlc: str,
    start_date: str,
    end_date: str,
    api_key: APIKey = Depends(require_api_key),
):
    """
    Generate FDA-compliant CSV spreadsheet for FSMA 204 audit.
    
    Args:
        tlc: Traceability Lot Code to trace
        start_date: Start date filter (YYYY-MM-DD)
        end_date: End date filter (YYYY-MM-DD)
        
    Returns:
        Downloadable CSV file
    """
    # For now, generate with empty events (graph integration pending)
    # In production, this would query the Neo4j graph
    csv_content = generate_fda_spreadsheet(
        tlc=tlc,
        start_date=start_date,
        end_date=end_date,
        events=[],
        facilities=[],
    )
    
    # Return as downloadable CSV
    filename = f"fsma_audit_{tlc.replace('/', '_')}_{start_date}_to_{end_date}.csv"
    
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
        },
    )


@app.post("/fsma/validate-tlc")
def validate_tlc(
    tlc: str,
    api_key: APIKey = Depends(require_api_key),
):
    """
    Validate a Traceability Lot Code format.
    
    Args:
        tlc: Traceability Lot Code to validate
        
    Returns:
        Validation result with error message if invalid
    """
    is_valid, error = fsma_engine.validate_tlc(tlc)
    return {
        "tlc": tlc,
        "valid": is_valid,
        "error": error,
    }


@app.get("/documents/{document_id}/analysis", response_model=AnalysisSummary)
async def get_document_analysis(
    document_id: str,
    api_key: APIKey = Depends(require_api_key),
):
    """
    Get AI analysis summary for an ingested document.
    
    Provides immediate insights including risk score and obligation counts.
    """
    return await analysis_engine.analyze_document(document_id)


@app.get("/drift/health")
def get_drift_health(
    api_key: APIKey = Depends(require_api_key),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Get current FSMA compliance drift health and alerts.
    
    Returns metrics on trace completeness, latency, and active alerts.
    """
    # Use real tenant context
    return drift_engine.check_health(tenant_id=str(tenant_id))

# ============================================================================
# Example Usage (for documentation)
# ============================================================================

@app.get("/examples/hipaa")
def example_hipaa_validation():
    """
    Example: HIPAA compliance validation

    Shows sample request/response for healthcare compliance check
    """
    return {
        "description": "Example HIPAA compliance check",
        "request": {
            "checklist_id": "hipaa_compliance",
            "customer_config": {
                "hipaa_001": True,
                "hipaa_002": True,
                "hipaa_003": True,
                "hipaa_004": False,  # FAIL
                "hipaa_005": True,
                "hipaa_006": False,  # FAIL
                "hipaa_007": True,
                "hipaa_008": True,
            }
        },
        "expected_response": {
            "overall_status": "WARNING",
            "pass_rate": 0.75,
            "items_failed": 2,
            "next_steps": [
                "Address 2 failed requirements",
                "→ Enable audit logging for PHI access",
                "→ Document breach notification process for 500+ affected individuals"
            ]
        }
    }


@app.get("/examples/finance")
def example_finance_validation():
    """
    Example: Finance capital requirements validation

    Shows sample request/response for financial compliance check
    """
    return {
        "description": "Example finance capital requirements check",
        "request": {
            "checklist_id": "capital_requirements",
            "customer_config": {
                "cap_001": 500000,  # $500k net capital
                "cap_002": 7.5,     # 7.5% Tier 1 ratio
                "cap_003": 95.0,    # 95% LCR (FAIL)
            }
        },
        "expected_response": {
            "overall_status": "WARNING",
            "pass_rate": 0.67,
            "items_failed": 1,
            "next_steps": [
                "Address 1 failed requirement",
                "→ Increase high-quality liquid assets to meet 100% LCR minimum"
            ]
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
