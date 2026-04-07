"""
Regulatory Obligation Engine - Data Models
==========================================
Pydantic models for obligation evaluation and tracking.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum


class Regulator(str, Enum):
    """Regulatory agencies."""
    OCC = "OCC"
    CFPB = "CFPB"
    FRB = "FRB"
    FDIC = "FDIC"
    NCUA = "NCUA"
    FDA = "FDA"


class RegulatoryDomain(str, Enum):
    """Regulatory domains."""
    FSMA = "FSMA"


class RiskLevel(str, Enum):
    """Risk severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ObligationDefinition(BaseModel):
    """
    Regulatory obligation definition.
    Loaded from obligations.yaml.
    """
    id: str = Field(..., description="Unique obligation ID (e.g., FSMA_204_CTE_RECEIVING)")
    citation: str = Field(..., description="Legal citation (e.g., 12 CFR 1002.9)")
    regulator: Regulator
    domain: RegulatoryDomain
    description: str = Field(..., min_length=10)
    triggering_conditions: Dict[str, Any] = Field(..., description="Conditions that trigger this obligation")
    required_evidence: List[str] = Field(..., min_length=1, description="Required evidence fields")


class ObligationEvaluationRequest(BaseModel):
    """Request to evaluate a decision against obligations."""
    decision_id: str
    decision_type: str
    decision_data: Dict[str, Any] = Field(..., description="Decision payload with evidence")
    vertical: str = Field(default="finance")


class ObligationMatch(BaseModel):
    """Result of matching a single obligation."""
    obligation_id: str
    citation: str
    regulator: Regulator
    domain: RegulatoryDomain
    met: bool = Field(..., description="Whether obligation is satisfied")
    missing_evidence: List[str] = Field(default_factory=list)
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Risk score for this violation")


class ObligationEvaluationResult(BaseModel):
    """Complete evaluation result."""
    evaluation_id: str
    decision_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    vertical: str
    
    # Evaluation results
    total_applicable_obligations: int
    met_obligations: int
    violated_obligations: int
    
    # Coverage metrics
    coverage_percent: float = Field(..., ge=0.0, le=100.0)
    overall_risk_score: float = Field(..., ge=0.0, le=1.0)
    risk_level: RiskLevel
    
    # Detailed matches
    obligation_matches: List[ObligationMatch]


class ObligationCoverageReport(BaseModel):
    """Aggregate obligation coverage report."""
    vertical: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    total_decisions_evaluated: int
    total_obligations: int
    
    # Coverage statistics
    average_coverage_percent: float
    min_coverage_percent: float
    max_coverage_percent: float
    
    # Violation statistics
    total_violations: int
    violations_by_domain: Dict[RegulatoryDomain, int]
    violations_by_regulator: Dict[Regulator, int]
    
    # Risk distribution
    decisions_by_risk_level: Dict[RiskLevel, int]


class RiskWeight(BaseModel):
    """Weighting for different risk factors in compliance scoring."""
    criticality: float = Field(0.5, ge=0.0, le=1.0)
    reputation_impact: float = Field(0.2, ge=0.0, le=1.0)
    legal_liability: float = Field(0.3, ge=0.0, le=1.0)


class ComplianceScore(BaseModel):
    """High-integrity compliance score result."""
    score: float = Field(..., ge=0.0, le=100.0)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    tenant_id: str
    vertical: str = "fsma"
    domain_scores: Dict[str, float] = Field(default_factory=dict)
    critical_findings_count: int = 0
    weights_used: RiskWeight
