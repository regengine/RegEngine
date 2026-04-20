"""
RegEngine - Compatibility Layer
===============================
This module re-exports models from kernel.obligation.models for backward compatibility.
Do not add new definitions here - add them to kernel.obligation.models instead.
"""

from kernel.obligation.models import (
    Regulator,
    RegulatoryDomain,
    RiskLevel,
    ObligationDefinition,
    ObligationEvaluationRequest,
    ObligationMatch,
    ObligationEvaluationResult,
    ObligationCoverageReport,
)

__all__ = [
    "Regulator",
    "RegulatoryDomain",
    "RiskLevel",
    "ObligationDefinition",
    "ObligationEvaluationRequest",
    "ObligationMatch",
    "ObligationEvaluationResult",
    "ObligationCoverageReport",
]
