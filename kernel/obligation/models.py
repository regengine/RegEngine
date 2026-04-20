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
    """Regulatory agencies.

    This engine is scoped to FSMA 204 (food safety) only.  Banking-sector
    agencies (OCC, CFPB, FRB, FDIC, NCUA) were listed here by mistake — they
    map to no ``RegulatoryDomain`` value and were never referenced by any
    obligation definition or test.  Removed in #1359.
    """
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


# ---------------------------------------------------------------------------
# RETIRED models — #1359
#
# RiskWeight and ComplianceScore were defined here but never imported or
# instantiated by any caller outside this file.  Each service that exposes a
# compliance score (services/ingestion, services/graph, services/admin) uses
# its own locally-defined response model.  These definitions are removed to
# eliminate dead code and the confusion they caused.
# ---------------------------------------------------------------------------
