"""
Auto-generated graph relationship definitions for Finance vertical.
DO NOT MODIFY MANUALLY - regenerate via: regengine compile vertical finance
"""

from enum import Enum


class FinanceRelationshipType(Enum):
    """Relationship types for Finance vertical graph."""
    
    USES_MODEL = "USES_MODEL"
    HAS_EVIDENCE = "HAS_EVIDENCE"
    VIOLATES = "VIOLATES"
    VERSION_PREVIOUS = "VERSION_PREVIOUS"
    VALIDATED_BY = "VALIDATED_BY"
    EXPERIENCED_DRIFT = "EXPERIENCED_DRIFT"
    EVALUATES = "EVALUATES"
    FOR_DECISION = "FOR_DECISION"
    AGAINST_OBLIGATION = "AGAINST_OBLIGATION"
    CHAIN_PREVIOUS = "CHAIN_PREVIOUS"


# Relationship metadata
RELATIONSHIP_METADATA = {
    "USES_MODEL": {
        "from": "FinanceDecision",
        "to": "ModelVersion",
        "properties": ["timestamp", "inference_latency_ms"]
    },
    "HAS_EVIDENCE": {
        "from": "FinanceDecision",
        "to": "EvidenceEnvelope",
        "properties": ["verified_at"]
    },
    "VIOLATES": {
        "from": "FinanceDecision",
        "to": "RegulatoryObligation",
        "properties": ["detected_at", "severity", "missing_evidence"]
    },
    "VERSION_PREVIOUS": {
        "from": "ModelVersion",
        "to": "ModelVersion",
        "properties": ["deployed_at"]
    },
    "VALIDATED_BY": {
        "from": "ModelVersion",
        "to": "BiasReport",
        "properties": ["validation_date"]
    },
    "EXPERIENCED_DRIFT": {
        "from": "ModelVersion",
        "to": "DriftEvent",
        "properties": ["detected_at"]
    },
    "EVALUATES": {
        "from": "ComplianceSnapshot",
        "to": "ModelVersion",
        "properties": ["evaluated_at"]
    },
    "FOR_DECISION": {
        "from": "ObligationEvaluation",
        "to": "FinanceDecision",
        "properties": ["evaluated_at"]
    },
    "AGAINST_OBLIGATION": {
        "from": "ObligationEvaluation",
        "to": "RegulatoryObligation",
        "properties": ["evaluated_at"]
    },
    "CHAIN_PREVIOUS": {
        "from": "EvidenceEnvelope",
        "to": "EvidenceEnvelope",
        "properties": ["hash_verified"]
    }
}
