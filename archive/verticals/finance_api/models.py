"""
Auto-generated Pydantic models for finance vertical.
DO NOT MODIFY MANUALLY - regenerate via: regengine compile vertical finance
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum


class DecisionType(str, Enum):
    """Decision types for finance vertical."""
    CREDIT_APPROVAL = "credit_approval"
    CREDIT_DENIAL = "credit_denial"
    LIMIT_ADJUSTMENT = "limit_adjustment"
    FRAUD_FLAG = "fraud_flag"
    ACCOUNT_CLOSURE = "account_closure"


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
    vertical: str = "finance"
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
