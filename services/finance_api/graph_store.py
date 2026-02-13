"""
Finance Graph Persistence Layer
===============================
Neo4j persistence for Finance vertical compliance data.

Replaces in-memory stores with graph database.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import json
import logging
from neo4j import GraphDatabase

logger = logging.getLogger(__name__)


class FinanceGraphStore:
    """
    Graph database persistence for Finance vertical.
    
    Stores:
    - Decisions
    - Obligation evaluations
    - Evidence envelopes
    - Bias reports
    - Drift events
    - Model versions
    """
    
    def __init__(self, uri: str, username: str, password: str):
        """
        Initialize graph store.
        
        Args:
            uri: Neo4j connection URI (e.g., "bolt://localhost:7687")
            username: Neo4j username
            password: Neo4j password
        """
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        logger.info(f"Connected to Neo4j at {uri}")
    
    def close(self):
        """Close Neo4j connection."""
        self.driver.close()
    
    def create_decision(
        self,
        decision_id: str,
        decision_type: str,
        evidence: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Create decision node in graph.
        
        Args:
            decision_id: Unique decision identifier
            decision_type: Type of decision
            evidence: Evidence payload
            metadata: Optional metadata
        """
        with self.driver.session() as session:
            session.write_transaction(
                self._create_decision_tx,
                decision_id,
                decision_type,
                evidence,
                metadata or {}
            )
        
        logger.info(f"Created decision node: {decision_id}")
    
    @staticmethod
    def _create_decision_tx(tx, decision_id, decision_type, evidence, metadata):
        """Transaction for creating decision node."""
        query = """
        CREATE (d:FinanceDecision {
            decision_id: $decision_id,
            decision_type: $decision_type,
            decision_date: datetime(),
            evidence: $evidence,
            metadata: $metadata
        })
        RETURN d.decision_id as decision_id
        """
        result = tx.run(
            query,
            decision_id=decision_id,
            decision_type=decision_type,
            evidence=json.dumps(evidence) if isinstance(evidence, dict) else str(evidence),
            metadata=json.dumps(metadata) if isinstance(metadata, dict) else str(metadata)
        )
        return result.single()
    
    def link_decision_to_model(
        self,
        decision_id: str,
        model_id: str,
        model_version: str
    ) -> None:
        """
        Create DECISION_USES_MODEL relationship.
        
        Args:
            decision_id: Decision identifier
            model_id: Model identifier
            model_version: Model version
        """
        with self.driver.session() as session:
            session.write_transaction(
                self._link_decision_to_model_tx,
                decision_id,
                model_id,
                model_version
            )
        
        logger.debug(f"Linked decision {decision_id} to model {model_id}")
    
    @staticmethod
    def _link_decision_to_model_tx(tx, decision_id, model_id, model_version):
        """Transaction for linking decision to model."""
        query = """
        MATCH (d:FinanceDecision {decision_id: $decision_id})
        MERGE (m:ModelVersion {model_id: $model_id})
        ON CREATE SET m.version = $model_version, m.created_date = datetime()
        CREATE (d)-[:DECISION_USES_MODEL {
            timestamp: datetime(),
            model_version: $model_version
        }]->(m)
        """
        tx.run(
            query,
            decision_id=decision_id,
            model_id=model_id,
            model_version=model_version
        )
    
    def create_obligation_evaluation(
        self,
        evaluation_id: str,
        decision_id: str,
        obligation_id: str,
        citation: str,
        status: str,
        required_evidence: List[str],
        provided_evidence: List[str]
    ) -> None:
        """
        Create obligation evaluation node.
        
        Args:
            evaluation_id: Evaluation identifier
            decision_id: Associated decision
            obligation_id: Obligation identifier
            citation: Regulatory citation
            status: 'met' or 'violated'
            required_evidence: Required evidence fields
            provided_evidence: Provided evidence fields
        """
        with self.driver.session() as session:
            session.write_transaction(
                self._create_obligation_evaluation_tx,
                evaluation_id,
                decision_id,
                obligation_id,
                citation,
                status,
                required_evidence,
                provided_evidence
            )
        
        logger.debug(f"Created obligation evaluation: {evaluation_id}")
    
    @staticmethod
    def _create_obligation_evaluation_tx(
        tx,
        evaluation_id,
        decision_id,
        obligation_id,
        citation,
        status,
        required_evidence,
        provided_evidence
    ):
        """Transaction for creating obligation evaluation."""
        query = """
        MATCH (d:FinanceDecision {decision_id: $decision_id})
        CREATE (oe:ObligationEvaluation {
            evaluation_id: $evaluation_id,
            obligation_id: $obligation_id,
            citation: $citation,
            status: $status,
            timestamp: datetime(),
            required_evidence: $required_evidence,
            provided_evidence: $provided_evidence
        })
        CREATE (d)-[:EVALUATED_AGAINST {
            timestamp: datetime(),
            status: $status
        }]->(oe)
        """
        tx.run(
            query,
            decision_id=decision_id,
            evaluation_id=evaluation_id,
            obligation_id=obligation_id,
            citation=citation,
            status=status,
            required_evidence=required_evidence,
            provided_evidence=provided_evidence
        )
    
    def create_evidence_envelope(
        self,
        envelope_id: str,
        decision_id: str,
        current_hash: str,
        previous_hash: Optional[str],
        merkle_root: str,
        evidence_payload_hash: str
    ) -> None:
        """
        Create evidence envelope node with hash chaining.
        
        Args:
            envelope_id: Envelope identifier
            decision_id: Associated decision
            current_hash: Current envelope hash
            previous_hash: Previous envelope hash (for chaining)
            merkle_root: Merkle tree root hash
            evidence_payload_hash: Evidence payload hash
        """
        with self.driver.session() as session:
            session.write_transaction(
                self._create_evidence_envelope_tx,
                envelope_id,
                decision_id,
                current_hash,
                previous_hash,
                merkle_root,
                evidence_payload_hash
            )
        
        logger.debug(f"Created evidence envelope: {envelope_id}")
    
    @staticmethod
    def _create_evidence_envelope_tx(
        tx,
        envelope_id,
        decision_id,
        current_hash,
        previous_hash,
        merkle_root,
        evidence_payload_hash
    ):
        """Transaction for creating evidence envelope."""
        query = """
        MATCH (d:FinanceDecision {decision_id: $decision_id})
        CREATE (env:EvidenceEnvelope {
            envelope_id: $envelope_id,
            timestamp: datetime(),
            current_hash: $current_hash,
            previous_hash: $previous_hash,
            merkle_root: $merkle_root,
            evidence_payload_hash: $evidence_payload_hash,
            tamper_detected: false
        })
        CREATE (d)-[:HAS_EVIDENCE {timestamp: datetime()}]->(env)
        
        // Create chain link if previous envelope exists
        WITH env
        MATCH (prev:EvidenceEnvelope {current_hash: $previous_hash})
        WHERE $previous_hash IS NOT NULL
        CREATE (env)-[:ENVELOPE_CHAINS_TO {timestamp: datetime()}]->(prev)
        """
        tx.run(
            query,
            decision_id=decision_id,
            envelope_id=envelope_id,
            current_hash=current_hash,
            previous_hash=previous_hash,
            merkle_root=merkle_root,
            evidence_payload_hash=evidence_payload_hash
        )
    
    def get_decision(self, decision_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve decision by ID.
        
        Args:
            decision_id: Decision identifier
        
        Returns:
            Decision data or None
        """
        with self.driver.session() as session:
            result = session.read_transaction(
                self._get_decision_tx,
                decision_id
            )
            return result
    
    @staticmethod
    def _get_decision_tx(tx, decision_id):
        """Transaction for getting decision."""
        query = """
        MATCH (d:FinanceDecision {decision_id: $decision_id})
        RETURN d {
            .*,
            decision_date: toString(d.decision_date)
        } as decision
        """
        result = tx.run(query, decision_id=decision_id)
        record = result.single()
        return record["decision"] if record else None
    
    def get_chain_stats(self) -> Dict[str, Any]:
        """
        Get evidence chain statistics.
        
        Returns:
            Chain statistics
        """
        with self.driver.session() as session:
            result = session.read_transaction(self._get_chain_stats_tx)
            return result
    
    @staticmethod
    def _get_chain_stats_tx(tx):
        """Transaction for getting chain stats."""
        query = """
        MATCH (env:EvidenceEnvelope)
        WITH count(env) as total_envelopes
        
        MATCH (d:FinanceDecision)
        WITH total_envelopes, count(d) as total_decisions
        
        MATCH (env:EvidenceEnvelope)
        WHERE env.previous_hash IS NULL
        RETURN {
            total_envelopes: total_envelopes,
            total_decisions: total_decisions,
            chain_head_hash: env.current_hash
        } as stats
        LIMIT 1
        """
        result = tx.run(query)
        record = result.single()
        return record["stats"] if record else {"total_envelopes": 0, "total_decisions": 0}
    
    def get_violations_by_model(self, model_id: str) -> List[Dict[str, Any]]:
        """
        Get all violations for a specific model.
        
        Args:
            model_id: Model identifier
        
        Returns:
            List of violations
        """
        with self.driver.session() as session:
            result = session.read_transaction(
                self._get_violations_by_model_tx,
                model_id
            )
            return result
    
    @staticmethod
    def _get_violations_by_model_tx(tx, model_id):
        """Transaction for getting violations by model."""
        query = """
        MATCH (m:ModelVersion {model_id: $model_id})<-[:DECISION_USES_MODEL]-(d:FinanceDecision)
        MATCH (d)-[:EVALUATED_AGAINST]->(oe:ObligationEvaluation)
        WHERE oe.status = 'violated'
        RETURN {
            decision_id: d.decision_id,
            decision_type: d.decision_type,
            obligation_id: oe.obligation_id,
            citation: oe.citation,
            timestamp: toString(oe.timestamp)
        } as violation
        ORDER BY oe.timestamp DESC
        """
        result = tx.run(query, model_id=model_id)
        return [record["violation"] for record in result]

    def create_bias_report(
        self,
        report_id: str,
        model_id: str,
        bias_detected: bool,
        dir_score: float,
        metrics: Dict[str, Any]
    ) -> None:
        """Create bias report node."""
        with self.driver.session() as session:
            session.write_transaction(
                self._create_bias_report_tx,
                report_id, model_id, bias_detected, dir_score, metrics
            )
            
    @staticmethod
    def _create_bias_report_tx(tx, report_id, model_id, bias_detected, dir_score, metrics):
        query = """
        MATCH (m:ModelVersion {model_id: $model_id})
        CREATE (b:BiasReport {
            report_id: $report_id,
            timestamp: datetime(),
            vertical: 'finance',
            bias_detected: $bias_detected,
            dir_score: $dir_score,
            metrics: $metrics
        })
        CREATE (m)-[:HAS_BIAS_CHECK {timestamp: datetime()}]->(b)
        """
        tx.run(query, report_id=report_id, model_id=model_id, 
               bias_detected=bias_detected, dir_score=dir_score,
               metrics=json.dumps(metrics) if isinstance(metrics, dict) else str(metrics))

    def create_drift_event(
        self,
        event_id: str,
        model_id: str,
        psi_score: float,
        drift_detected: bool,
        feature_scores: Dict[str, float]
    ) -> None:
        """Create drift event node."""
        with self.driver.session() as session:
            session.write_transaction(
                self._create_drift_event_tx,
                event_id, model_id, psi_score, drift_detected, feature_scores
            )

    @staticmethod
    def _create_drift_event_tx(tx, event_id, model_id, psi_score, drift_detected, feature_scores):
        query = """
        MATCH (m:ModelVersion {model_id: $model_id})
        CREATE (d:DriftEvent {
            event_id: $event_id,
            timestamp: datetime(),
            vertical: 'finance',
            drift_detected: $drift_detected,
            psi_score: $psi_score,
            feature_scores: $feature_scores
        })
        CREATE (m)-[:HAS_DRIFT_CHECK {timestamp: datetime()}]->(d)
        """
        tx.run(query, event_id=event_id, model_id=model_id, 
               psi_score=psi_score, drift_detected=drift_detected,
               feature_scores=json.dumps(feature_scores) if isinstance(feature_scores, dict) else str(feature_scores))
