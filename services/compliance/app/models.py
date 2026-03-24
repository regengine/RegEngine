from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# FSMA 204 Models
# ---------------------------------------------------------------------------

ModelStatus = Literal["active", "deprecated"]
ValidationType = Literal["fairness", "performance", "conceptual_soundness"]
ChangeType = Literal["feature_added", "threshold_change", "retrain"]


class ModelRegistrationRequest(BaseModel):
    id: str = Field(..., min_length=2)
    name: str = Field(..., min_length=2)
    version: str = Field(..., min_length=1)
    owner: str = Field(..., min_length=2)
    deployment_date: date
    status: ModelStatus = "active"


class ValidationRequest(BaseModel):
    validation_type: ValidationType
    validator: str = Field(..., min_length=2)
    date: date
    status: Literal["passed", "failed"]
    notes: Optional[str] = None


class ModelChangeRequest(BaseModel):
    change_type: ChangeType
    description: str = Field(..., min_length=4)
    date: date


class ModelRecordResponse(BaseModel):
    id: str
    name: str
    version: str
    owner: str
    deployment_date: date
    status: ModelStatus
    deployment_locked: bool
    lock_reason: Optional[str]
    last_fairness_result_at: Optional[datetime] = None


AuditOutputType = Literal[
    "regulator_examination_package",
    "fair_lending_summary_report",
    "model_validation_dossier",
    "bias_incident_timeline",
]


class AuditExportRequest(BaseModel):
    model_id: str = Field(..., min_length=2)
    output_type: AuditOutputType
    reviewer: str = Field(..., min_length=2)


class AuditExportResponse(BaseModel):
    artifact_id: str
    model_id: str
    output_type: AuditOutputType
    version: int
    immutable: bool
    hash_sha256: str
    generated_at: datetime
    metadata: Dict[str, str]


class RiskSummaryResponse(BaseModel):
    overall_fair_lending_risk: Literal["Low", "Medium", "High"]
    dir_status: Literal["Green", "Yellow", "Red"]
    regression_bias_flag: bool
    drift_status: Literal["Green", "Yellow", "Red"]
    last_tested: date
    exposure_score: float


class CKGSummaryResponse(BaseModel):
    nodes_by_type: Dict[str, int]
    edge_count: int
    latest_evidence_id: Optional[str]
