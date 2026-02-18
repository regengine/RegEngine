"""
Weighted Compliance Scoring Engine
==================================
Calculates high-integrity compliance scores for FSMA and other domains.
"""

from typing import List, Dict, Any
from .models import ComplianceScore, RiskWeight, ObligationMatch, RiskLevel

def calculate_compliance_score(
    tenant_id: str,
    matches: List[ObligationMatch],
    weights: RiskWeight = RiskWeight(),
    vertical: str = "fsma"
) -> ComplianceScore:
    """
    Calculate a weighted compliance score based on obligation matches.
    
    Formula:
        Raw Score = (Met Obligations / Total Obligations) * 100
        Adjusted Score = Raw Score * (1 - Weighted Risk Penalty)
    """
    if not matches:
        return ComplianceScore(
            score=100.0,
            tenant_id=tenant_id,
            vertical=vertical,
            weights_used=weights
        )

    total_count = len(matches)
    met_count = sum(1 for m in matches if m.met)
    
    # Calculate domain scores
    domain_scores: Dict[str, List[float]] = {}
    critical_findings = 0
    risk_accum = 0.0
    
    for match in matches:
        domain = str(match.domain)
        if domain not in domain_scores:
            domain_scores[domain] = []
        
        domain_scores[domain].append(1.0 if match.met else 0.0)
        
        if not match.met:
            # Penalize based on risk_score
            risk_accum += match.risk_score
            if match.risk_score >= 0.8:  # Heuristic for critical
                critical_findings += 1

    # Average domain scores
    final_domain_scores = {
        d: (sum(scores) / len(scores)) * 100.0 
        for d, scores in domain_scores.items()
    }
    
    # Calculate weighted penalty
    # Penalty is capped at 1.0 (100% reduction)
    # Weights from RiskWeight: criticality, reputation_impact, legal_liability
    penalty_factor = (risk_accum / total_count) * (weights.criticality + weights.legal_liability)
    penalty_factor = min(1.0, penalty_factor)
    
    raw_score = (met_count / total_count) * 100.0
    final_score = raw_score * (1.0 - (penalty_factor * 0.5)) # Adjust impact of penalty
    
    return ComplianceScore(
        score=max(0.0, round(final_score, 2)),
        tenant_id=tenant_id,
        vertical=vertical,
        domain_scores=final_domain_scores,
        critical_findings_count=critical_findings,
        weights_used=weights
    )
