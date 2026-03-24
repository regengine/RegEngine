# Archived fair-lending models — extracted from services/compliance/app/models.py
# These types supported the fair-lending analysis pipeline (ECOA/FHA/CFPB) and are
# not part of the FSMA 204 product surface.

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
