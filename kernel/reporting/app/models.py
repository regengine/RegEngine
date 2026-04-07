"""
Pydantic Models for Compliance API.

Defines schemas for checklists, validation requests, and FSMA assessments.
"""

from typing import Any, Dict, List, Optional
from enum import Enum
from pydantic import BaseModel, Field


class ChecklistListResponse(BaseModel):
    """List of available compliance checklists"""
    checklists: List[Dict[str, Any]]
    total: int


class ValidationRequest(BaseModel):
    """Request to validate compliance against a checklist"""
    checklist_id: str = Field(..., description="ID of the compliance checklist")
    customer_config: Dict[str, Any] = Field(
        ...,
        description="Customer configuration/answers keyed by requirement ID",
        example={
            "fsma_204_cte_receiving": True,
            "fsma_204_cte_shipping": True,
            "fsma_204_kde_completeness": False,
        }
    )


class ValidationItemResponse(BaseModel):
    """Validation result for a single checklist item"""
    requirement_id: str
    requirement: str
    regulation: str
    status: str  # PASS, FAIL, WARNING, NOT_APPLICABLE
    evidence: Optional[str] = None
    remediation: Optional[str] = None


class ValidationResponse(BaseModel):
    """Complete validation result"""
    checklist_id: str
    checklist_name: str
    industry: str
    jurisdiction: str
    overall_status: str  # PASS, FAIL, WARNING
    pass_rate: float = Field(..., description="Pass rate as decimal (0.0-1.0)")
    items: List[ValidationItemResponse]
    next_steps: List[str]


class TraceabilityPlanModel(BaseModel):
    plan_document: Optional[str] = None
    plan_owner: Optional[str] = None
    update_frequency_months: Optional[int] = None
    training_program: Optional[str] = None
    product_scope: List[str] = Field(default_factory=list)
    digital_workflow: Optional[bool] = None
    kpi_dashboard: Optional[bool] = None


class KDECaptureModel(BaseModel):
    receiving: List[str] = Field(default_factory=list)
    transformation: List[str] = Field(default_factory=list)
    shipping: List[str] = Field(default_factory=list)
    cooling: List[str] = Field(default_factory=list)


class RecordkeepingModel(BaseModel):
    retention_years: Optional[int] = None
    retrieval_time_hours: Optional[int] = None
    digital_system: bool = False
    storage_format: Optional[str] = None
    system_of_record: Optional[str] = None


class TechnologyModel(BaseModel):
    capabilities: List[str] = Field(default_factory=list)
    integration_notes: Optional[str] = None


class FSMAAssessmentRequest(BaseModel):
    """FSMA 204 facility profile input"""

    facility_name: str = Field(..., description="Facility under evaluation")
    facility_type: Optional[str] = Field(None, description="e.g., RTE salads, seafood processor")
    products: List[str] = Field(default_factory=list)
    traceability_plan: TraceabilityPlanModel = Field(default_factory=TraceabilityPlanModel)
    kde_capture: KDECaptureModel = Field(default_factory=KDECaptureModel)
    critical_tracking_events: List[str] = Field(default_factory=list)
    recordkeeping: RecordkeepingModel = Field(default_factory=RecordkeepingModel)
    technology: TechnologyModel = Field(default_factory=TechnologyModel)


class DimensionScoreModel(BaseModel):
    id: str
    name: str
    weight: float
    score: float
    status: str
    rationale: str
    gaps: List[str]


class FSMAAssessmentResponse(BaseModel):
    rule_name: str
    regulator: str
    effective_date: Optional[str]
    facility_name: str
    overall_score: float
    risk_level: str
    dimension_scores: List[DimensionScoreModel]
    remediation_actions: List[str]


class AnalysisRisk(BaseModel):
    id: str
    description: str
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW


class AnalysisSummary(BaseModel):
    document_id: str
    status: str  # PROCESSING, COMPLETE, ERROR
    risk_score: int
    obligations_count: int
    missing_dates_count: int
    critical_risks: List[AnalysisRisk]

