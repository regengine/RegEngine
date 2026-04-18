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
    
    def __init__(self, verticals_dir, graph_client=None, db_client=None):
        """
        Initialize regulatory engine.
        
        Args:
            verticals_dir: Path to verticals directory (str or Path)
            graph_client: Neo4j graph client (optional)
            db_client: Database client (optional)
        """
        # Convert to Path if string
        self.verticals_dir = Path(verticals_dir) if isinstance(verticals_dir, str) else verticals_dir
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
        
        with open(obligations_path, encoding="utf-8") as f:
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
        vertical: str = "food_beverage",
        tenant_id: str = "",
    ) -> ObligationEvaluationResult:
        """
        Evaluate a decision against obligations.

        Args:
            decision_id: Unique decision ID
            decision_type: Type of decision
            decision_data: Decision payload
            vertical: Vertical name (e.g. "food_beverage")
            tenant_id: Tenant identifier for cross-tenant isolation

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
        self._persist_evaluation(result, tenant_id=tenant_id)

        return result
    
    def _persist_evaluation(self, result: ObligationEvaluationResult, tenant_id: str = ""):
        """
        Persist evaluation result to graph and database.

        Creates one ObligationEvaluation node per obligation match, then links
        each node to its parent Decision and the matching RegulatoryObligation.

        Graph structure per match:
            (ObligationEvaluation)-[:FOR_DECISION]->(Decision)
            (ObligationEvaluation)-[:AGAINST_OBLIGATION]->(RegulatoryObligation)

        Hardening (#1326):

        * Single ``UNWIND``-based Cypher inside a managed
          ``session.execute_write`` transaction — O(1) round-trips instead of
          O(3N), atomic on connection failure.
        * Both the Decision and RegulatoryObligation MATCH clauses now
          filter on ``tenant_id`` so a cross-tenant id collision cannot
          stitch an evaluation into the wrong subgraph.

        Args:
            result: The evaluation result to persist.
            tenant_id: Tenant identifier for cross-tenant isolation.
        """
        if self.graph is None:
            logger.warning("No graph client configured, skipping persistence")
            return

        if not result.obligation_matches:
            # Nothing to persist; avoid an empty UNWIND round-trip.
            return

        matches_payload = [
            {
                "obligation_id": m.obligation_id,
                "met": m.met,
                "missing_evidence": list(m.missing_evidence),
                "risk_score": m.risk_score,
            }
            for m in result.obligation_matches
        ]

        cypher = """
        UNWIND $matches AS m
        CREATE (oe:ObligationEvaluation {
            evaluation_id: $evaluation_id,
            tenant_id: $tenant_id,
            vertical: $vertical,
            decision_id: $decision_id,
            obligation_id: m.obligation_id,
            met: m.met,
            missing_evidence: m.missing_evidence,
            evaluated_at: datetime($evaluated_at),
            risk_score: m.risk_score
        })
        WITH oe, m
        OPTIONAL MATCH (d:Decision {decision_id: $decision_id, tenant_id: $tenant_id})
        FOREACH (_ IN CASE WHEN d IS NOT NULL THEN [1] ELSE [] END |
            MERGE (oe)-[:FOR_DECISION]->(d)
        )
        WITH oe, m
        OPTIONAL MATCH (o:RegulatoryObligation {obligation_id: m.obligation_id, tenant_id: $tenant_id})
        FOREACH (_ IN CASE WHEN o IS NOT NULL THEN [1] ELSE [] END |
            MERGE (oe)-[:AGAINST_OBLIGATION]->(o)
        )
        """

        params = {
            "matches": matches_payload,
            "evaluation_id": result.evaluation_id,
            "tenant_id": tenant_id,
            "vertical": result.vertical,
            "decision_id": result.decision_id,
            "evaluated_at": result.timestamp.isoformat(),
        }

        def _write(tx):
            tx.run(cypher, **params)

        try:
            with self.graph.session() as session:
                # ``execute_write`` wraps the body in a managed transaction
                # with automatic retry on transient errors — so a mid-batch
                # connection drop either lands everything or nothing.
                if hasattr(session, "execute_write"):
                    session.execute_write(_write)
                else:  # pragma: no cover - test doubles
                    session.run(cypher, **params)

                logger.info(
                    "persisted evaluation %s to Neo4j (%d obligation nodes)",
                    result.evaluation_id,
                    len(result.obligation_matches),
                )
        except Exception as e:
            logger.error("Failed to persist evaluation to graph: %s", e)
    
    def get_coverage_report(self, vertical: str = "food_beverage", tenant_id: str = "") -> Dict[str, Any]:
        """
        Generate aggregate coverage report for a vertical.

        Args:
            vertical: Vertical name
            tenant_id: Tenant identifier for cross-tenant isolation

        Returns:
            Coverage statistics
        """
        if self.graph is None:
            logger.warning("No graph client configured, returning empty coverage report")
            return {
                "vertical": vertical,
                "status": "graph_unavailable",
                "total_obligations": 0,
                "evaluated_obligations": 0,
                "met_obligations": 0,
                "coverage_percent": 0.0
            }

        try:
            with self.graph.session() as session:
                # Get total obligations for this vertical
                total_result = session.run(
                    """
                    MATCH (o:RegulatoryObligation {vertical: $vertical, tenant_id: $tenant_id})
                    RETURN count(o) as total
                    """,
                    vertical=vertical,
                    tenant_id=tenant_id,
                )
                total_obligations = total_result.single()["total"]

                # Get evaluated obligations (recent evaluations)
                evaluated_result = session.run(
                    """
                    MATCH (oe:ObligationEvaluation {vertical: $vertical, tenant_id: $tenant_id})
                    WHERE oe.evaluated_at > datetime() - duration('P30D')
                    RETURN count(DISTINCT oe.obligation_id) as evaluated,
                           sum(CASE WHEN oe.met THEN 1 ELSE 0 END) as met
                    """,
                    vertical=vertical,
                    tenant_id=tenant_id,
                )
                eval_record = evaluated_result.single()
                evaluated_obligations = eval_record["evaluated"] or 0
                met_obligations = eval_record["met"] or 0

                # Get recent evaluations for trend analysis
                trend_result = session.run(
                    """
                    MATCH (oe:ObligationEvaluation {vertical: $vertical, tenant_id: $tenant_id})
                    WHERE oe.evaluated_at > datetime() - duration('P7D')
                    RETURN
                        count(oe) as recent_evaluations,
                        avg(CASE WHEN oe.met THEN 1.0 ELSE 0.0 END) as recent_compliance_rate,
                        avg(oe.risk_score) as avg_confidence
                    """,
                    vertical=vertical,
                    tenant_id=tenant_id,
                )
                trend_record = trend_result.single()
                
                coverage_percent = (evaluated_obligations / total_obligations * 100) if total_obligations > 0 else 0.0
                
                logger.info(f"Coverage report for {vertical}: {coverage_percent:.1f}% ({evaluated_obligations}/{total_obligations})")
                
                return {
                    "vertical": vertical,
                    "status": "success",
                    "total_obligations": total_obligations,
                    "evaluated_obligations": evaluated_obligations,
                    "met_obligations": met_obligations,
                    "coverage_percent": round(coverage_percent, 2),
                    "recent_evaluations_7d": trend_record["recent_evaluations"] or 0,
                    "recent_compliance_rate": round(trend_record["recent_compliance_rate"] or 0.0, 4),
                    "avg_confidence": round(trend_record["avg_confidence"] or 0.0, 4)
                }
        except Exception as e:
            logger.error(f"Failed to generate coverage report: {e}")
            return {
                "vertical": vertical,
                "status": "error",
                "error": str(e)
            }
