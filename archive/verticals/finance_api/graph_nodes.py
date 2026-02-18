"""
Auto-generated graph node definitions for Finance vertical.
DO NOT MODIFY MANUALLY - regenerate via: regengine compile vertical finance
"""

from neomodel import (
    StructuredNode,
    StringProperty,
    DateTimeProperty,
    FloatProperty,
    IntegerProperty,
    BooleanProperty,
    JSONProperty,
    UniqueIdProperty,
    RelationshipTo,
    RelationshipFrom
)
from datetime import datetime


class FinanceDecision(StructuredNode):
    """Represents a single AI-driven decision in the Finance domain."""
    
    decision_id = UniqueIdProperty()
    decision_type = StringProperty(required=True, choices=['credit_approval', 'credit_denial', 'limit_adjustment', 'fraud_flag', 'account_closure'])
    timestamp = DateTimeProperty(default_now=True)
    customer_id = StringProperty(required=True, index=True)
    model_version_id = StringProperty(required=True, index=True)
    decision_outcome = StringProperty(required=True)
    confidence_score = FloatProperty()
    evidence_hash = StringProperty(index=True)
    
    # Relationships
    uses_model = RelationshipTo('ModelVersion', 'USES_MODEL')
    has_evidence = RelationshipTo('EvidenceEnvelope', 'HAS_EVIDENCE')
    violates = RelationshipTo('RegulatoryObligation', 'VIOLATES')
    evaluations = RelationshipFrom('ObligationEvaluation', 'FOR_DECISION')


class ModelVersion(StructuredNode):
    """Represents a specific version of an AI model."""
    
    version_id = UniqueIdProperty()
    model_name = StringProperty(required=True, index=True)
    version = StringProperty(required=True)
    deployed_at = DateTimeProperty(default_now=True)
    training_data_hash = StringProperty()
    validation_report_hash = StringProperty()
    bias_baseline_hash = StringProperty()
    architecture = StringProperty()
    performance_metrics = JSONProperty()
    
    # Relationships
    version_previous = RelationshipTo('ModelVersion', 'VERSION_PREVIOUS')
    decisions = RelationshipFrom('FinanceDecision', 'USES_MODEL')
    validated_by = RelationshipTo('BiasReport', 'VALIDATED_BY')
    drift_events = RelationshipTo('DriftEvent', 'EXPERIENCED_DRIFT')


class RegulatoryObligation(StructuredNode):
    """Represents a specific regulatory requirement."""
    
    obligation_id = UniqueIdProperty()
    citation = StringProperty(required=True, index=True)
    regulator = StringProperty(required=True, choices=['OCC', 'CFPB', 'FRB', 'FDIC', 'NCUA'])
    domain = StringProperty(required=True, choices=['ECOA', 'TILA', 'FCRA', 'UDAAP', 'SR_11_7', 'OCC_AI'])
    description = StringProperty(required=True)
    triggering_conditions = JSONProperty()
    required_evidence = JSONProperty()
    
    # Relationships
    violations = RelationshipFrom('FinanceDecision', 'VIOLATES')
    evaluations = RelationshipFrom('ObligationEvaluation', 'AGAINST_OBLIGATION')


class BiasReport(StructuredNode):
    """Statistical bias analysis result."""
    
    report_id = UniqueIdProperty()
    timestamp = DateTimeProperty(default_now=True)
    model_version_id = StringProperty(required=True)
    protected_class = StringProperty(required=True)
    disparate_impact_ratio = FloatProperty()
    eighty_percent_rule_pass = BooleanProperty()
    chi_square_statistic = FloatProperty()
    chi_square_p_value = FloatProperty()
    fisher_exact_p_value = FloatProperty()
    statistical_significance = BooleanProperty()
    sample_size_control = IntegerProperty()
    sample_size_protected = IntegerProperty()
    
    # Relationships
    validates = RelationshipFrom('ModelVersion', 'VALIDATED_BY')


class DriftEvent(StructuredNode):
    """Model drift detection event."""
    
    event_id = UniqueIdProperty()
    timestamp = DateTimeProperty(default_now=True)
    model_version_id = StringProperty(required=True)
    drift_type = StringProperty(required=True, choices=['data_drift', 'prediction_drift', 'concept_drift'])
    psi_score = FloatProperty()
    kl_divergence = FloatProperty()
    js_divergence = FloatProperty()
    confidence_mean_baseline = FloatProperty()
    confidence_mean_current = FloatProperty()
    confidence_variance_baseline = FloatProperty()
    confidence_variance_current = FloatProperty()
    threshold_exceeded = BooleanProperty()
    severity = StringProperty(required=True, choices=['low', 'medium', 'high', 'critical'])
    
    # Relationships
    model = RelationshipFrom('ModelVersion', 'EXPERIENCED_DRIFT')


class ComplianceSnapshot(StructuredNode):
    """Point-in-time compliance state."""
    
    snapshot_id = UniqueIdProperty()
    timestamp = DateTimeProperty(default_now=True)
    vertical = StringProperty(default='finance')
    bias_score = FloatProperty()
    drift_score = FloatProperty()
    documentation_score = FloatProperty()
    regulatory_mapping_score = FloatProperty()
    obligation_coverage_percent = FloatProperty()
    total_compliance_score = FloatProperty()
    risk_level = StringProperty(choices=['low', 'medium', 'high', 'critical'])
    num_open_violations = IntegerProperty()
    
    # Relationships
    evaluates = RelationshipTo('ModelVersion', 'EVALUATES')


class EvidenceEnvelope(StructuredNode):
    """Cryptographic evidence record (EvidenceEnvelopeV3)."""
    
    envelope_id = UniqueIdProperty()
    timestamp = DateTimeProperty(default_now=True)
    current_hash = StringProperty(required=True, index=True)
    previous_hash = StringProperty()
    merkle_root = StringProperty()
    merkle_proof = JSONProperty()
    evidence_type = StringProperty()
    evidence_payload_hash = StringProperty()
    tamper_detected = BooleanProperty(default=False)
    
    # Relationships
    chain_previous = RelationshipTo('EvidenceEnvelope', 'CHAIN_PREVIOUS')
    decision = RelationshipFrom('FinanceDecision', 'HAS_EVIDENCE')


class ObligationEvaluation(StructuredNode):
    """Result of evaluating decision against obligations."""
   
    evaluation_id = UniqueIdProperty()
    timestamp = DateTimeProperty(default_now=True)
    decision_id = StringProperty(required=True)
    obligation_id = StringProperty(required=True)
    met = BooleanProperty(required=True)
    missing_evidence = JSONProperty()
    risk_score = FloatProperty()
    
    # Relationships
    for_decision = RelationshipTo('FinanceDecision', 'FOR_DECISION')
    against_obligation = RelationshipTo('RegulatoryObligation', 'AGAINST_OBLIGATION')
