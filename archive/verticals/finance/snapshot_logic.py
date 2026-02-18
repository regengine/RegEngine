"""
Finance Vertical - Snapshot Computation Logic
==============================================
Implements snapshot scoring functions for Finance AI Governance vertical.

Each function computes a score [0.0, 100.0] for a specific compliance dimension.
"""

from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


def compute_bias_score(bias_reports: List[Dict[str, Any]]) -> float:
    """
    Compute bias score based on bias testing reports.
    
    Score Formula:
    - 100.0 if all protected classes pass 80% rule
    - Deduct 20 points per protected class that fails
    - Deduct additional 10 points if statistically significant
    
    Args:
        bias_reports: List of BiasReport dicts from graph
        
    Returns:
        Bias score [0.0, 100.0]
    """
    if not bias_reports:
        logger.warning("No bias reports found, defaulting to score 50")
        return 50.0
    
    base_score = 100.0
    
    for report in bias_reports:
        # Check 80% rule pass
        if not report.get('eighty_percent_rule_pass', False):
            base_score -= 20.0
            
            # Additional penalty if statistically significant
            if report.get('statistical_significance', False):
                base_score -= 10.0
    
    return max(0.0, base_score)


def compute_drift_score(drift_events: List[Dict[str, Any]]) -> float:
    """
    Compute drift score based on model drift events.
    
    Score Formula:
    - 100.0 if no drift events detected
    - Deduct points based on drift severity and recency
    
    Args:
        drift_events: List of DriftEvent dicts from graph
        
    Returns:
        Drift score [0.0, 100.0]
    """
    if not drift_events:
        return 100.0  # No drift = perfect score
    
    base_score = 100.0
    
    # Severity penalties
    severity_penalties = {
        'low': 5.0,
        'medium': 15.0,
        'high': 30.0,
        'critical': 50.0
    }
    
    for event in drift_events:
        severity = event.get('severity', 'medium')
        penalty = severity_penalties.get(severity, 15.0)
        base_score -= penalty
    
    return max(0.0, base_score)


def compute_documentation_score(
    decisions: List[Dict[str, Any]],
    models: List[Dict[str, Any]]
) -> float:
    """
    Compute documentation score based on model documentation completeness.
    
    Score Formula:
    - Check % of models with complete documentation
    - Check % of decisions with required evidence
    
    Args:
        decisions: List of decision dicts from graph
        models: List of ModelVersion dicts from graph
        
    Returns:
        Documentation score [0.0, 100.0]
    """
    # Model documentation completeness
    required_model_fields = [
        'training_data_hash',
        'validation_report_hash',
        'bias_baseline_hash'
    ]
    
    if models:
        documented_models = sum(
            1 for model in models
            if all(model.get(field) for field in required_model_fields)
        )
        model_score = (documented_models / len(models)) * 100
    else:
        model_score = 50.0  # Neutral if no models
    
    # Decision evidence completeness
    if decisions:
        complete_decisions = sum(
            1 for decision in decisions
            if decision.get('evidence_hash')  # Has evidence attached
        )
        decision_score = (complete_decisions / len(decisions)) * 100
    else:
        decision_score = 100.0  # No decisions = no violations
    
    # Weighted average
    documentation_score = (model_score * 0.6) + (decision_score * 0.4)
    
    return documentation_score


def compute_regulatory_mapping_score(
    obligation_evaluations: List[Dict[str, Any]]
) -> float:
    """
    Compute regulatory mapping score based on obligation coverage.
    
    Score Formula:
    - % of obligations met
    - Weighted by obligation risk_score
    
    Args:
        obligation_evaluations: List of ObligationEvaluation dicts from graph
        
    Returns:
        Regulatory mapping score [0.0, 100.0]
    """
    if not obligation_evaluations:
        logger.warning("No obligation evaluations found, defaulting to score 50")
        return 50.0
    
    # Compute weighted coverage
    total_weight = 0.0
    met_weight = 0.0
    
    for evaluation in obligation_evaluations:
        # Use risk_score as weight (higher risk = higher weight)
        weight = evaluation.get('risk_score', 0.5)
        total_weight += weight
        
        if evaluation.get('met', False):
            met_weight += weight
    
    if total_weight == 0:
        return 50.0
    
    coverage_pct = (met_weight / total_weight) * 100
    
    return coverage_pct


def compute_obligation_coverage_percent(
    obligation_evaluations: List[Dict[str, Any]]
) -> float:
    """
    Compute simple obligation coverage percentage.
    
    Args:
        obligation_evaluations: List of ObligationEvaluation dicts from graph
        
    Returns:
        Coverage percentage [0.0, 100.0]
    """
    if not obligation_evaluations:
        return 0.0
    
    met_count = sum(1 for e in obligation_evaluations if e.get('met', False))
    total_count = len(obligation_evaluations)
    
    coverage = (met_count / total_count) * 100
    
    return coverage


def compute_total_compliance_score(
    bias_score: float,
    drift_score: float,
    documentation_score: float,
    regulatory_mapping_score: float,
    scoring_weights: Dict[str, float]
) -> float:
    """
    Compute weighted total compliance score.
    
    Args:
        bias_score: Bias score [0-100]
        drift_score: Drift score [0-100]
        documentation_score: Documentation score [0-100]
        regulatory_mapping_score: Regulatory mapping score [0-100]
        scoring_weights: Weights dict from vertical.yaml
        
    Returns:
        Total compliance score [0.0, 100.0]
    """
    total = (
        bias_score * scoring_weights['bias'] +
        drift_score * scoring_weights['drift'] +
        documentation_score * scoring_weights['documentation'] +
        regulatory_mapping_score * scoring_weights['regulatory_mapping']
    )
    
    return total
