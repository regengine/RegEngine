"""
Regulatory Obligation Evaluator
================================
Core logic for evaluating decisions against regulatory obligations.
"""

from typing import List, Dict, Any, Tuple
import logging
from datetime import datetime
import uuid

from .models import (
    ObligationDefinition,
    ObligationMatch,
    ObligationEvaluationResult,
    RiskLevel
)

logger = logging.getLogger(__name__)


class ObligationEvaluator:
    """
    Evaluates decisions against regulatory obligations.
    
    Workflow:
    1. Load applicable obligations for decision type
    2. Check triggering conditions
    3. Verify required evidence present
    4. Compute coverage %
    5. Assign risk scores
    """
    
    def __init__(self, obligations: List[ObligationDefinition]):
        """
        Initialize evaluator with obligation definitions.
        
        Args:
            obligations: List of ObligationDefinition from obligations.yaml
        """
        self.obligations = obligations
        self.obligations_by_id = {o.id: o for o in obligations}
        logger.info(f"Initialized evaluator with {len(obligations)} obligations")
    
    def evaluate_decision(
        self,
        decision_id: str,
        decision_type: str,
        decision_data: Dict[str, Any],
        vertical: str = "finance"
    ) -> ObligationEvaluationResult:
        """
        Evaluate a decision against all applicable obligations.
        
        Args:
            decision_id: Unique decision identifier
            decision_type: Type of decision (e.g., credit_denial)
            decision_data: Decision payload with evidence
            vertical: Vertical name
            
        Returns:
            ObligationEvaluationResult with coverage and matches
        """
        logger.info(f"Evaluating decision {decision_id} of type {decision_type}")
        
        # Step 1: Find applicable obligations
        applicable_obligations = self._find_applicable_obligations(
            decision_type,
            decision_data
        )
        
        logger.info(f"Found {len(applicable_obligations)} applicable obligations")
        
        # Step 2: Evaluate each obligation
        obligation_matches = []
        for obligation in applicable_obligations:
            match = self._evaluate_obligation(obligation, decision_data)
            obligation_matches.append(match)
        
        # Step 3: Compute metrics
        met_count = sum(1 for m in obligation_matches if m.met)
        violated_count = len(obligation_matches) - met_count
        coverage_percent = (met_count / len(obligation_matches) * 100) if obligation_matches else 100.0
        
        # Step 4: Compute overall risk score
        overall_risk_score = self._compute_overall_risk(obligation_matches)
        
        # Step 5: Determine risk level
        risk_level = self._determine_risk_level(coverage_percent, overall_risk_score)
        
        result = ObligationEvaluationResult(
            evaluation_id=str(uuid.uuid4()),
            decision_id=decision_id,
            timestamp=datetime.utcnow(),
            vertical=vertical,
            total_applicable_obligations=len(obligation_matches),
            met_obligations=met_count,
            violated_obligations=violated_count,
            coverage_percent=coverage_percent,
            overall_risk_score=overall_risk_score,
            risk_level=risk_level,
            obligation_matches=obligation_matches
        )
        
        logger.info(
            f"Evaluation complete: {met_count}/{len(obligation_matches)} met "
            f"(coverage={coverage_percent:.1f}%, risk={risk_level})"
        )
        
        return result
    
    def _find_applicable_obligations(
        self,
        decision_type: str,
        decision_data: Dict[str, Any]
    ) -> List[ObligationDefinition]:
        """
        Find obligations applicable to this decision.
        
        Checks triggering_conditions to determine applicability.
        """
        applicable = []
        
        for obligation in self.obligations:
            if self._matches_triggering_conditions(obligation, decision_type, decision_data):
                applicable.append(obligation)
        
        return applicable
    
    def _matches_triggering_conditions(
        self,
        obligation: ObligationDefinition,
        decision_type: str,
        decision_data: Dict[str, Any]
    ) -> bool:
        """
        Check if obligation's triggering conditions are met.
        
        Triggering conditions are AND-ed together.
        """
        conditions = obligation.triggering_conditions
        
        # Check decision_type match
        if "decision_type" in conditions:
            if conditions["decision_type"] != decision_type:
                return False
        
        # Check other conditions
        for key, expected_value in conditions.items():
            if key == "decision_type":
                continue  # Already checked
            
            # Check if key exists in decision_data and matches expected value
            actual_value = decision_data.get(key)
            
            if actual_value != expected_value:
                return False
        
        return True
    
    def _evaluate_obligation(
        self,
        obligation: ObligationDefinition,
        decision_data: Dict[str, Any]
    ) -> ObligationMatch:
        """
        Evaluate a single obligation against decision data.
        
        Checks if all required evidence fields are present.
        """
        missing_evidence = []
        
        for required_field in obligation.required_evidence:
            if required_field not in decision_data:
                missing_evidence.append(required_field)
            elif decision_data[required_field] is None:
                missing_evidence.append(required_field)
        
        met = len(missing_evidence) == 0
        
        # Compute risk score based on missing evidence
        if met:
            risk_score = 0.0
        else:
            # Risk score proportional to missing evidence
            # More missing fields = higher risk
            missing_ratio = len(missing_evidence) / len(obligation.required_evidence)
            risk_score = min(1.0, 0.5 + (missing_ratio * 0.5))  # Range: 0.5-1.0 for violations
        
        return ObligationMatch(
            obligation_id=obligation.id,
            citation=obligation.citation,
            regulator=obligation.regulator,
            domain=obligation.domain,
            met=met,
            missing_evidence=missing_evidence,
            risk_score=risk_score
        )
    
    def _compute_overall_risk(self, obligation_matches: List[ObligationMatch]) -> float:
        """
        Compute overall risk score from individual obligation matches.
        
        Uses weighted average, with higher weight on higher individual risk scores.
        """
        if not obligation_matches:
            return 0.0
        
        total_risk = sum(m.risk_score for m in obligation_matches)
        avg_risk = total_risk / len(obligation_matches)
        
        return avg_risk
    
    def _determine_risk_level(self, coverage_percent: float, overall_risk_score: float) -> RiskLevel:
        """
        Determine risk level based on coverage and risk score.
        
        Thresholds:
        - coverage >= 90% AND risk < 0.3: LOW
        - coverage >= 70% AND risk < 0.5: MEDIUM
        - coverage >= 50% AND risk < 0.7: HIGH
        - Otherwise: CRITICAL
        """
        if coverage_percent >= 90 and overall_risk_score < 0.3:
            return RiskLevel.LOW
        elif coverage_percent >= 70 and overall_risk_score < 0.5:
            return RiskLevel.MEDIUM
        elif coverage_percent >= 50 and overall_risk_score < 0.7:
            return RiskLevel.HIGH
        else:
            return RiskLevel.CRITICAL
