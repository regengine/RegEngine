"""
Regulatory Obligation Engine - Main Service
============================================
Orchestrates obligation loading, evaluation, and persistence.
"""

import yaml
from pathlib import Path
from typing import Optional, Dict, Any
import logging

from .models import ObligationDefinition, ObligationEvaluationResult
from .evaluator import ObligationEvaluator

logger = logging.getLogger(__name__)


class RegulatoryEngine:
    """
    Main service for regulatory obligation management.
    
    Responsibilities:
    - Load obligations from YAML
    - Orchestrate evaluation
    - Persist results to graph + DB
    """
    
    def __init__(self, verticals_dir: Path, graph_client=None, db_client=None):
        """
        Initialize regulatory engine.
        
        Args:
            verticals_dir: Path to verticals directory
            graph_client: Neo4j graph client (optional)
            db_client: Database client (optional)
        """
        self.verticals_dir = verticals_dir
        self.graph = graph_client
        self.db = db_client
        self.evaluators: Dict[str, ObligationEvaluator] = {}
        
        logger.info("Regulatory Engine initialized")
    
    def load_vertical_obligations(self, vertical_name: str) -> ObligationEvaluator:
        """
        Load obligations for a vertical from obligations.yaml.
        
        Args:
            vertical_name: Name of vertical (e.g., 'finance')
            
        Returns:
            ObligationEvaluator instance
        """
        if vertical_name in self.evaluators:
            logger.info(f"Using cached evaluator for {vertical_name}")
            return self.evaluators[vertical_name]
        
        obligations_path = self.verticals_dir / vertical_name / "obligations.yaml"
        
        if not obligations_path.exists():
            raise FileNotFoundError(f"obligations.yaml not found at {obligations_path}")
        
        with open(obligations_path) as f:
            data = yaml.safe_load(f)
        
        obligations = [
            ObligationDefinition(**obligation)
            for obligation in data.get("obligations", [])
        ]
        
        logger.info(f"Loaded {len(obligations)} obligations for {vertical_name}")
        
        evaluator = ObligationEvaluator(obligations)
        self.evaluators[vertical_name] = evaluator
        
        return evaluator
    
    def evaluate_decision(
        self,
        decision_id: str,
        decision_type: str,
        decision_data: Dict[str, Any],
        vertical: str = "finance"
    ) -> ObligationEvaluationResult:
        """
        Evaluate a decision against obligations.
        
        Args:
            decision_id: Unique decision ID
            decision_type: Type of decision
            decision_data: Decision payload
            vertical: Vertical name
            
        Returns:
            ObligationEvaluationResult
        """
        # Load evaluator for vertical
        evaluator = self.load_vertical_obligations(vertical)
        
        # Perform evaluation
        result = evaluator.evaluate_decision(
            decision_id=decision_id,
            decision_type=decision_type,
            decision_data=decision_data,
            vertical=vertical
        )
        
        # Persist result
        self._persist_evaluation(result)
        
        return result
    
    def _persist_evaluation(self, result: ObligationEvaluationResult):
        """
        Persist evaluation result to graph and database.
        
        Creates:
        - ObligationEvaluation nodes in graph
        - FOR_DECISION relationships
        - AGAINST_OBLIGATION relationships
        """
        if self.graph is None:
            logger.warning("No graph client configured, skipping persistence")
            return
        
        # TODO: Implement graph persistence
        # - Create ObligationEvaluation node for each match
        # - Link to FinanceDecision via FOR_DECISION
        # - Link to RegulatoryObligation via AGAINST_OBLIGATION
        
        logger.info(f"Persisted evaluation {result.evaluation_id}")
    
    def get_coverage_report(self, vertical: str = "finance") -> Dict[str, Any]:
        """
        Generate aggregate coverage report for a vertical.
        
        Args:
            vertical: Vertical name
            
        Returns:
            Coverage statistics
        """
        # TODO: Implement coverage report from persisted evaluations
        
        return {
            "vertical": vertical,
            "status": "not_implemented"
        }
