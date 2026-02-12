"""
Neo4j Graph Migration for Finance Vertical
==========================================
Creates graph schema for Finance compliance tracking.

Nodes:
- FinanceDecision
- ModelVersion
- ObligationEvaluation
- BiasReport
- DriftEvent
- EvidenceEnvelope

Relationships:
- DECISION_USES_MODEL
- DECISION_VIOLATES_OBLIGATION
- DECISION_TRIGGERS_BIAS_REPORT
- MODEL_EXPERIENCED_DRIFT
- ENVELOPE_CHAINS_TO
"""

// ============================================================================
// CONSTRAINTS
// ============================================================================

// Decision constraints
CREATE CONSTRAINT finance_decision_id IF NOT EXISTS
FOR (d:FinanceDecision) REQUIRE d.decision_id IS UNIQUE;

CREATE INDEX finance_decision_date IF NOT EXISTS
FOR (d:FinanceDecision) ON (d.decision_date);

CREATE INDEX finance_decision_type IF NOT EXISTS
FOR (d:FinanceDecision) ON (d.decision_type);

// Model constraints
CREATE CONSTRAINT model_id IF NOT EXISTS
FOR (m:ModelVersion) REQUIRE m.model_id IS UNIQUE;

// Obligation constraints
CREATE CONSTRAINT obligation_id IF NOT EXISTS
FOR (o:ObligationEvaluation) REQUIRE o.evaluation_id IS UNIQUE;

// Evidence constraints
CREATE CONSTRAINT envelope_id IF NOT EXISTS
FOR (e:EvidenceEnvelope) REQUIRE e.envelope_id IS UNIQUE;

CREATE INDEX envelope_hash IF NOT EXISTS
FOR (e:EvidenceEnvelope) ON (e.current_hash);

// Bias report constraints
CREATE CONSTRAINT bias_report_id IF NOT EXISTS
FOR (b:BiasReport) REQUIRE b.report_id IS UNIQUE;

// Drift event constraints
CREATE CONSTRAINT drift_event_id IF NOT EXISTS
FOR (d:DriftEvent) REQUIRE d.event_id IS UNIQUE;


// ============================================================================
// SAMPLE DATA (for testing)
// ============================================================================

// Create sample model
CREATE (m:ModelVersion {
  model_id: 'credit_model_v1',
  version: '1.0.0',
  created_date: datetime(),
  algorithm: 'logistic_regression',
  features: ['credit_score', 'income', 'debt_to_income'],
  performance_metrics: {
    accuracy: 0.85,
    auc: 0.88
  }
});

// Create sample decision with evidence
CREATE (d:FinanceDecision {
  decision_id: 'dec_001',
  decision_type: 'credit_denial',
  decision_date: datetime(),
  applicant_id: 'app_12345',
  evidence: {
    adverse_action_notice: 'Your application has been denied',
    reason_codes: ['insufficient_credit_history'],
    notification_timing: 'within_30_days'
  }
});

// Create obligation evaluation
CREATE (oe:ObligationEvaluation {
  evaluation_id: 'eval_001',
  obligation_id: 'ECOA_ADVERSE_ACTION_NOTICE',
  citation: '12 CFR 1002.9(a)(1)',
  regulator: 'CFPB',
  domain: 'ECOA',
  status: 'met',
  timestamp: datetime(),
  required_evidence: ['adverse_action_notice', 'reason_codes'],
  provided_evidence: ['adverse_action_notice', 'reason_codes']
});

// Create evidence envelope with hash chain
CREATE (env:EvidenceEnvelope {
  envelope_id: 'env_001',
  timestamp: datetime(),
  current_hash: 'a1b2c3d4e5f6',
  previous_hash: null,
  merkle_root: 'merkle_root_hash',
  evidence_type: 'DECISION',
  tamper_detected: false
});

// Create bias report
CREATE (br:BiasReport {
  report_id: 'bias_001',
  model_id: 'credit_model_v1',
  timestamp: datetime(),
  protected_class: 'race',
  reference_group: 'white',
  protected_group: 'black',
  disparate_impact_ratio: 0.75,
  passes_80_rule: false,
  statistically_significant: true,
  severity: 'moderate'
});

// Create drift event
CREATE (de:DriftEvent {
  event_id: 'drift_001',
  model_id: 'credit_model_v1',
  feature_name: 'credit_score',
  timestamp: datetime(),
  psi: 0.35,
  kl_divergence: 0.28,
  js_divergence: 0.15,
  severity: 'moderate',
  alert_triggered: true
});


// ============================================================================
// RELATIONSHIPS
// ============================================================================

// Link decision to model
MATCH (d:FinanceDecision {decision_id: 'dec_001'})
MATCH (m:ModelVersion {model_id: 'credit_model_v1'})
CREATE (d)-[:DECISION_USES_MODEL {
  timestamp: datetime(),
  model_version: '1.0.0'
}]->(m);

// Link decision to obligation evaluation
MATCH (d:FinanceDecision {decision_id: 'dec_001'})
MATCH (oe:ObligationEvaluation {evaluation_id: 'eval_001'})
CREATE (d)-[:EVALUATED_AGAINST {
  timestamp: datetime(),
  coverage_percent: 85.0,
  risk_level: 'medium'
}]->(oe);

// Link decision to evidence envelope
MATCH (d:FinanceDecision {decision_id: 'dec_001'})
MATCH (env:EvidenceEnvelope {envelope_id: 'env_001'})
CREATE (d)-[:HAS_EVIDENCE {
  timestamp: datetime()
}]->(env);

// Link model to bias report
MATCH (m:ModelVersion {model_id: 'credit_model_v1'})
MATCH (br:BiasReport {report_id: 'bias_001'})
CREATE (m)-[:TRIGGERS_BIAS_REPORT {
  timestamp: datetime(),
  severity: 'moderate'
}]->(br);

// Link model to drift event
MATCH (m:ModelVersion {model_id: 'credit_model_v1'})
MATCH (de:DriftEvent {event_id: 'drift_001'})
CREATE (m)-[:EXPERIENCED_DRIFT {
  timestamp: datetime(),
  severity: 'moderate'
}]->(de);


// ============================================================================
// QUERIES
// ============================================================================

// Query 1: Find all decisions with violations
MATCH (d:FinanceDecision)-[:EVALUATED_AGAINST]->(oe:ObligationEvaluation)
WHERE oe.status = 'violated'
RETURN d.decision_id, d.decision_type, oe.obligation_id, oe.citation
ORDER BY d.decision_date DESC;

// Query 2: Find all bias reports failing 80% rule
MATCH (m:ModelVersion)-[:TRIGGERS_BIAS_REPORT]->(br:BiasReport)
WHERE br.passes_80_rule = false
RETURN m.model_id, br.protected_class, br.disparate_impact_ratio, br.severity
ORDER BY br.timestamp DESC;

// Query 3: Find all drift events above alert threshold
MATCH (m:ModelVersion)-[:EXPERIENCED_DRIFT]->(de:DriftEvent)
WHERE de.alert_triggered = true
RETURN m.model_id, de.feature_name, de.psi, de.severity
ORDER BY de.psi DESC;

// Query 4: Traverse evidence chain
MATCH path = (head:EvidenceEnvelope)-[:ENVELOPE_CHAINS_TO*]->(tail:EvidenceEnvelope)
WHERE head.previous_hash IS NULL
RETURN path, length(path) as chain_length;

// Query 5: Get compliance snapshot for model
MATCH (m:ModelVersion {model_id: 'credit_model_v1'})
OPTIONAL MATCH (m)-[:TRIGGERS_BIAS_REPORT]->(br:BiasReport)
OPTIONAL MATCH (m)-[:EXPERIENCED_DRIFT]->(de:DriftEvent)
OPTIONAL MATCH (d:FinanceDecision)-[:DECISION_USES_MODEL]->(m)
OPTIONAL MATCH (d)-[:EVALUATED_AGAINST]->(oe:ObligationEvaluation)
RETURN 
  m.model_id,
  count(DISTINCT d) as total_decisions,
  count(DISTINCT br) as bias_reports,
  count(DISTINCT de) as drift_events,
  count(DISTINCT CASE WHEN oe.status = 'violated' THEN oe END) as violations,
  avg(CASE WHEN oe.status = 'met' THEN 1.0 ELSE 0.0 END) * 100 as coverage_percent;

// Query 6: Find decisions by protected class (for bias analysis)
MATCH (d:FinanceDecision)
WHERE d.evidence.race IS NOT NULL
RETURN 
  d.evidence.race as protected_class,
  d.decision_type,
  count(*) as count,
  sum(CASE WHEN d.decision_type IN ['credit_approval', 'limit_adjustment'] THEN 1 ELSE 0 END) as approvals,
  sum(CASE WHEN d.decision_type = 'credit_denial' THEN 1 ELSE 0 END) as denials
GROUP BY d.evidence.race, d.decision_type
ORDER BY protected_class, decision_type;
