from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


RiskCategory = Literal["disparate_impact", "disparate_treatment", "documentation"]
ControlType = Literal["statistical_test", "documentation", "monitoring"]
FrequencyType = Literal["real_time", "monthly", "quarterly"]
MethodologyType = Literal["DIR", "regression", "KS_test", "feature_importance"]


class RegulationMapRequest(BaseModel):
    source_name: str = Field(..., min_length=2)
    citation: str = Field(..., min_length=2)
    section: str = Field(..., min_length=1)
    text: str = Field(..., min_length=10)
    effective_date: Optional[date] = None


class GeneratedTest(BaseModel):
    test_name: str
    methodology: MethodologyType
    metric_definition: str
    failure_threshold: str


class GeneratedControl(BaseModel):
    control_name: str
    control_type: ControlType
    frequency: FrequencyType
    threshold_value: str
    tests: List[GeneratedTest]


class GeneratedObligation(BaseModel):
    obligation_text: str
    risk_category: RiskCategory
    controls: List[GeneratedControl]


class RegulationMapResponse(BaseModel):
    regulation_id: str
    obligations: List[GeneratedObligation]


AnalysisType = Literal["DIR", "regression", "drift"]


class GroupOutcome(BaseModel):
    name: str = Field(..., min_length=1)
    approved: int = Field(..., ge=0)
    denied: int = Field(..., ge=0)


class FairLendingAnalyzeRequest(BaseModel):
    model_id: str = Field(..., min_length=2)
    protected_attribute: str = Field(..., min_length=2)
    groups: List[GroupOutcome] = Field(..., min_length=2)
    analysis_type: List[AnalysisType] = Field(default_factory=lambda: ["DIR", "regression", "drift"])
    historical_approval_rates: Optional[Dict[str, List[float]]] = None


class DirResult(BaseModel):
    group_name: str
    approval_rate: float
    disparate_impact_ratio: float
    flagged: bool


class ThresholdSimulationResult(BaseModel):
    threshold_delta_percent: int
    projected_dir: float
    risk_band: Literal["green", "yellow", "red"]


class RegressionResult(BaseModel):
    coefficient: float
    p_value: float
    statistically_significant: bool
    methodology: str


class DriftResult(BaseModel):
    protected_group: str
    baseline_rate: float
    current_rate: float
    ks_statistic: float
    flagged: bool


class FairLendingAnalyzeResponse(BaseModel):
    model_id: str
    analysis_id: str
    dir_results: List[DirResult]
    regression_bias_flag: bool
    drift_flag: bool
    risk_level: Literal["low", "medium", "high"]
    recommended_action: str
    threshold_sensitivity: List[ThresholdSimulationResult]
    regression_result: Optional[RegressionResult] = None
    drift_results: List[DriftResult] = Field(default_factory=list)
    analyzed_at: datetime


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
