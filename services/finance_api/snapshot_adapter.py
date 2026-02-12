"""
Auto-generated snapshot adapter for Finance vertical.
DO NOT MODIFY MANUALLY - regenerate via: regengine compile vertical finance
"""

from typing import Dict, List, Any
from datetime import datetime
import logging

from verticals.finance.snapshot_logic import (
    compute_bias_score,
    compute_drift_score,
    compute_documentation_score,
    compute_regulatory_mapping_score,
    compute_obligation_coverage_percent
)

logger = logging.getLogger(__name__)


# Scoring weights from vertical.yaml
SCORING_WEIGHTS = {'bias': 0.3, 'drift': 0.2, 'documentation': 0.25, 'regulatory_mapping': 0.25}


class FinanceSnapshotAdapter:
    """
    Snapshot adapter for Finance vertical.
    
    Computes compliance snapshot by aggregating scores from multiple dimensions.
    """
    
    def __init__(self, graph_client, db_client):
        self.graph = graph_client
        self.db = db_client
    
    def compute_snapshot(self) -> Dict[str, Any]:
        """
        Compute current compliance snapshot.
        
        Returns:
            Snapshot with scores across all dimensions
        """
        logger.info("Computing Finance compliance snapshot")
        
        # Gather data from graph and DB
        decisions = self._fetch_decisions()
        models = self._fetch_models()
        bias_reports = self._fetch_bias_reports()
        drift_events = self._fetch_drift_events()
        obligation_evaluations = self._fetch_obligation_evaluations()
        
        # Compute individual scores
        bias_score = compute_bias_score(bias_reports)
        drift_score = compute_drift_score(drift_events)
        documentation_score = compute_documentation_score(decisions, models)
        regulatory_mapping_score = compute_regulatory_mapping_score(obligation_evaluations)
        obligation_coverage = compute_obligation_coverage_percent(obligation_evaluations)
        
        # Compute weighted total score
        total_score = (
            bias_score * SCORING_WEIGHTS['bias'] +
            drift_score * SCORING_WEIGHTS['drift'] +
            documentation_score * SCORING_WEIGHTS['documentation'] +
            regulatory_mapping_score * SCORING_WEIGHTS['regulatory_mapping']
        )
        
        # Determine risk level
        risk_level = self._determine_risk_level(total_score, obligation_evaluations)
        
        # Count open violations
        num_open_violations = sum(1 for eval in obligation_evaluations if not eval['met'])
        
        snapshot = {
            'snapshot_id': str(uuid.uuid4()),
            'timestamp': datetime.utcnow().isoformat(),
            'vertical': 'finance',
            'bias_score': bias_score,
            'drift_score': drift_score,
            'documentation_score': documentation_score,
            'regulatory_mapping_score': regulatory_mapping_score,
            'obligation_coverage_percent': obligation_coverage,
            'total_compliance_score': total_score,
            'risk_level': risk_level,
            'num_open_violations': num_open_violations
        }
        
        # Persist snapshot
        self._persist_snapshot(snapshot)
        
        logger.info(f"Snapshot computed: total_score={total_score:.2f}, risk={risk_level}")
        
        return snapshot
    
    def _fetch_decisions(self) -> List[Dict]:
        """Fetch recent decisions from graph."""
        if not self.graph:
            logger.warning("No graph client available, returning empty decisions")
            return []
        
        try:
            # Query Neo4j for recent finance decisions
            with self.graph.session() as session:
                result = session.run(
                    """
                    MATCH (d:Decision)
                    WHERE d.vertical = 'finance'
                    RETURN d
                    ORDER BY d.created_at DESC
                    LIMIT 100
                    """
                )
                decisions = [dict(record['d']) for record in result]
                logger.debug(f"Fetched {len(decisions)} decisions from graph")
                return decisions
        except Exception as e:
            logger.error(f"Failed to fetch decisions from graph: {e}")
            return []
    
    def _fetch_models(self) -> List[Dict]:
        """Fetch model versions from graph."""
        if not self.graph:
            logger.warning("No graph client available, returning empty models")
            return []
        
        try:
            # Query Neo4j for finance model versions
            with self.graph.session() as session:
                result = session.run(
                    """
                    MATCH (m:Model)
                    WHERE m.vertical = 'finance'
                    RETURN m
                    ORDER BY m.version DESC
                    LIMIT 50
                    """
                )
                models = [dict(record['m']) for record in result]
                logger.debug(f"Fetched {len(models)} models from graph")
                return models
        except Exception as e:
            logger.error(f"Failed to fetch models from graph: {e}")
            return []
    
    def _fetch_bias_reports(self) -> List[Dict]:
        """Fetch bias reports from graph."""
        if not self.graph:
            logger.warning("No graph client available, returning empty bias reports")
            return []
        
        try:
            # Query Neo4j for bias reports
            with self.graph.session() as session:
                result = session.run(
                    """
                    MATCH (b:BiasReport)
                    WHERE b.vertical = 'finance'
                    RETURN b
                    ORDER BY b.timestamp DESC
                    LIMIT 50
                    """
                )
                reports = [dict(record['b']) for record in result]
                logger.debug(f"Fetched {len(reports)} bias reports from graph")
                return reports
        except Exception as e:
            logger.error(f"Failed to fetch bias reports from graph: {e}")
            return []
    
    def _fetch_drift_events(self) -> List[Dict]:
        """Fetch drift events from graph."""
        if not self.graph:
            logger.warning("No graph client available, returning empty drift events")
            return []
        
        try:
            # Query Neo4j for drift events
            with self.graph.session() as session:
                result = session.run(
                    """
                    MATCH (e:DriftEvent)
                    WHERE e.vertical = 'finance'
                    RETURN e
                    ORDER BY e.timestamp DESC
                    LIMIT 50
                    """
                )
                events = [dict(record['e']) for record in result]
                logger.debug(f"Fetched {len(events)} drift events from graph")
                return events
        except Exception as e:
            logger.error(f"Failed to fetch drift events from graph: {e}")
            return []
    
    def _fetch_obligation_evaluations(self) -> List[Dict]:
        """Fetch obligation evaluations from graph."""
        if not self.graph:
            logger.warning("No graph client available, returning empty obligations")
            return []
        
        try:
            # Query Neo4j for obligation evaluations
            with self.graph.session() as session:
                result = session.run(
                    """
                    MATCH (o:ObligationEvaluation)
                    WHERE o.vertical = 'finance'
                    RETURN o
                    ORDER BY o.timestamp DESC
                    LIMIT 100
                    """
                )
                evaluations = [dict(record['o']) for record in result]
                logger.debug(f"Fetched {len(evaluations)} obligation evaluations from graph")
                return evaluations
        except Exception as e:
            logger.error(f"Failed to fetch obligation evaluations from graph: {e}")
            return []
    
    def _determine_risk_level(self, total_score: float, evaluations: List[Dict]) -> str:
        """
        Determine risk level based on total score and open violations.
        
        Thresholds:
        - total_score >= 80: low
        - total_score >= 60: medium
        - total_score >= 40: high
        - total_score < 40: critical
        """
        critical_violations = [e for e in evaluations if not e['met'] and e.get('risk_score', 0) > 0.8]
        
        if critical_violations:
            return 'critical'
        elif total_score >= 80:
            return 'low'
        elif total_score >= 60:
            return 'medium'
        elif total_score >= 40:
            return 'high'
        else:
            return 'critical'
    
    def _persist_snapshot(self, snapshot: Dict):
        """Persist snapshot to graph and DB."""
        # Persist to Neo4j if available
        if self.graph:
            try:
                with self.graph.session() as session:
                    session.run(
                        """
                        CREATE (s:ComplianceSnapshot {
                            snapshot_id: $snapshot_id,
                            timestamp: $timestamp,
                            vertical: $vertical,
                            bias_score: $bias_score,
                            drift_score: $drift_score,
                            documentation_score: $documentation_score,
                            regulatory_mapping_score: $regulatory_mapping_score,
                            obligation_coverage_percent: $obligation_coverage_percent,
                            total_compliance_score: $total_compliance_score,
                            risk_level: $risk_level,
                            num_open_violations: $num_open_violations
                        })
                        """,
                        **snapshot
                    )
                    logger.info(f"Persisted snapshot {snapshot['snapshot_id']} to graph")
            except Exception as e:
                logger.error(f"Failed to persist snapshot to graph: {e}")
        
        # Persist to DB if available
        if self.db:
            try:
                from sqlalchemy import text
                
                # Insert snapshot into PostgreSQL
                # Note: Table schema should be created via Alembic migration
                insert_query = text("""
                    INSERT INTO finance_snapshots (
                        snapshot_id, timestamp, vertical,
                        bias_score, drift_score, documentation_score,
                        regulatory_mapping_score, obligation_coverage_percent,
                        total_compliance_score, risk_level,
                        num_open_violations, data, created_at
                    ) VALUES (
                        :snapshot_id, :timestamp, :vertical,
                        :bias_score, :drift_score, :documentation_score,
                        :regulatory_mapping_score, :obligation_coverage_percent,
                        :total_compliance_score, :risk_level,
                        :num_open_violations, :data::jsonb, NOW()
                    )
                    ON CONFLICT (snapshot_id) DO UPDATE SET
                        timestamp = EXCLUDED.timestamp,
                        bias_score = EXCLUDED.bias_score,
                        drift_score = EXCLUDED.drift_score,
                        total_compliance_score = EXCLUDED.total_compliance_score,
                        risk_level = EXCLUDED.risk_level,
                        data = EXCLUDED.data
                """)
                
                import json
                with self.db.begin() as conn:
                    conn.execute(insert_query, {
                        **snapshot,
                        'data': json.dumps(snapshot)  # Store full snapshot as JSONB
                    })
                
                logger.info(f"Persisted snapshot {snapshot['snapshot_id']} to PostgreSQL")
            except Exception as e:
                logger.error(f"Failed to persist snapshot to DB: {e}")


import uuid
