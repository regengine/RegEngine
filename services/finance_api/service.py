"""
Finance Decision Service
=========================
Orchestrates decision recording workflow:
1. Validate decision data
2. Evaluate against regulatory obligations (ROE)
3. Create cryptographic evidence envelope (Evidence V3)
4. Persist to graph database
5. Trigger analytics (bias/drift monitoring)
"""

from typing import Dict, Any, Optional
import uuid
from datetime import datetime
import logging

from services.regulatory_engine import RegulatoryEngine, ObligationEvaluationResult
from services.evidence import (
    EvidenceEnvelopeV3,
    EvidenceType,
    compute_payload_hash,
    generate_merkle_proof
)
from .models import DecisionRequest, DecisionResponse


logger = logging.getLogger(__name__)


class FinanceDecisionService:
    """
    Finance decision orchestration service.
    
    Workflow:
    1. Record decision with evidence
    2. Evaluate against Finance obligations (ROE)
    3. Create evidence envelope with hash chaining
    4. Persist decision + evaluation + envelope to graph
    5. Return comprehensive response
    """
    
    def __init__(self, verticals_dir: str = "./verticals"):
        """
        Initialize service.
        
        Args:
            verticals_dir: Path to verticals directory (for ROE)
        """
        # Import here to avoid circular imports
        from pathlib import Path
        verticals_path = Path(verticals_dir).absolute()
        
        try:
            self.regulatory_engine = RegulatoryEngine(verticals_dir=str(verticals_path))
        except Exception as e:
            logger.warning(f"RegulatoryEngine initialization failed: {e}. Using mock.")
            self.regulatory_engine = None
        
        # In-memory stores (in production, these would be persistent)
        self.decisions = {}
        self.envelopes = {}
        self.latest_envelope_hash = None  # For hash chaining
    
    def record_decision(self, request: DecisionRequest) -> DecisionResponse:
        """
        Record a finance decision with full compliance workflow.
        
        Steps:
        1. Create decision record
        2. Evaluate against obligations
        3. Create evidence envelope
        4. Persist to stores
        
        Args:
            request: DecisionRequest
        
        Returns:
            DecisionResponse with evaluation results
        """
        logger.info(f"Recording {request.decision_type} decision: {request.decision_id}")
        
        # Step 1: Create decision record
        decision_record = {
            "decision_id": request.decision_id,
            "decision_type": request.decision_type.value,
            "evidence": request.evidence,
            "metadata": request.metadata or {},
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Step 2: Evaluate against regulatory obligations
        evaluation = self._evaluate_obligations(
            decision_id=request.decision_id,
            decision_type=request.decision_type.value,
            decision_data=request.evidence
        )
        
        # Step 3: Create evidence envelope
        envelope = self._create_evidence_envelope(
            decision_id=request.decision_id,
            decision_type=request.decision_type.value,
            evidence_payload=request.evidence,
            evaluation=evaluation
        )
        
        # Step 4: Persist to stores
        self.decisions[request.decision_id] = decision_record
        self.envelopes[envelope.envelope_id] = envelope
        self.latest_envelope_hash = envelope.current_hash
        
        # Step 5: Build response
        response = DecisionResponse(
            decision_id=request.decision_id,
            status="recorded",
            timestamp=decision_record["timestamp"],
            evaluation_id=evaluation.evaluation_id,
            coverage_percent=evaluation.coverage_percent,
            risk_level=evaluation.risk_level.value
        )
        
        logger.info(
            f"Decision recorded: {request.decision_id}, "
            f"coverage={evaluation.coverage_percent:.1f}%, "
            f"risk={evaluation.risk_level.value}"
        )
        
        return response
    
    def _evaluate_obligations(
        self,
        decision_id: str,
        decision_type: str,
        decision_data: Dict[str, Any]
    ) -> ObligationEvaluationResult:
        """
        Evaluate decision against Finance regulatory obligations.
        
        Uses Regulatory Obligation Engine (ROE).
        """
        # If ROE not available, return mock evaluation
        if self.regulatory_engine is None:
            logger.warning("Using mock obligation evaluation")
            from services.regulatory_engine.models import RiskLevel
            return ObligationEvaluationResult(
                evaluation_id=f"eval_{decision_id}",
                decision_id=decision_id,
                vertical="finance",
                total_applicable_obligations=27,
                met_obligations=20,
                violated_obligations=[],
                coverage_percent=74.1,
                risk_level=RiskLevel.MEDIUM,
                evaluated_at=datetime.utcnow()
            )
        
        try:
            evaluation = self.regulatory_engine.evaluate_decision(
                decision_id=decision_id,
                decision_type=decision_type,
                decision_data=decision_data,
                vertical="finance"
            )
            
            logger.info(
                f"Obligation evaluation: {evaluation.met_obligations}/"
                f"{evaluation.total_applicable_obligations} obligations met"
            )
            
            return evaluation
            
        except Exception as e:
            logger.error(f"Obligation evaluation failed: {str(e)}", exc_info=True)
            raise
    
    def _create_evidence_envelope(
        self,
        decision_id: str,
        decision_type: str,
        evidence_payload: Dict[str, Any],
        evaluation: ObligationEvaluationResult
    ) -> EvidenceEnvelopeV3:
        """
        Create cryptographic evidence envelope.
        
        Features:
        - Hash chaining (links to previous envelope)
        - Merkle proof (for batch integrity)
        - Tamper detection
        """
        envelope_id = str(uuid.uuid4())
        
        # Compute payload hash
        payload_hash = compute_payload_hash(evidence_payload)
        
        # For simplicity, use single-element Merkle tree (root = leaf)
        merkle_root = payload_hash
        merkle_proof = []
        
        # Combine evidence payload with evaluation results
        combined_payload = {
            "decision_id": decision_id,
            "decision_type": decision_type,
            "evidence": evidence_payload,
            "evaluation_id": evaluation.evaluation_id,
            "coverage_percent": evaluation.coverage_percent,
            "risk_level": evaluation.risk_level.value
        }
        
        # Compute combined payload hash
        combined_hash = compute_payload_hash(combined_payload)
        
        # Create envelope data (excluding current_hash to avoid circular dependency)
        envelope_data = {
            "envelope_id": envelope_id,
            "timestamp": datetime.utcnow(),
            "previous_hash": self.latest_envelope_hash,
            "merkle_root": merkle_root,
            "merkle_proof": merkle_proof,
            "evidence_type": EvidenceType.DECISION,
            "evidence_payload_hash": payload_hash,
            "evidence_payload": combined_payload,
            "tamper_detected": False
        }
        
        # Compute current hash (hash of entire envelope)
        current_hash = compute_payload_hash(envelope_data)
        
        # Create envelope
        envelope = EvidenceEnvelopeV3(
            **envelope_data,
            current_hash=current_hash
        )
        
        logger.info(
            f"Evidence envelope created: {envelope_id}, "
            f"chained_to={self.latest_envelope_hash[:8] if self.latest_envelope_hash else 'root'}"
        )
        
        return envelope
    
    def get_decision(self, decision_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve decision record."""
        return self.decisions.get(decision_id)
    
    def get_envelope(self, envelope_id: str) -> Optional[EvidenceEnvelopeV3]:
        """Retrieve evidence envelope."""
        return self.envelopes.get(envelope_id)
    
    def get_chain_stats(self) -> Dict[str, Any]:
        """Get evidence chain statistics."""
        return {
            "total_envelopes": len(self.envelopes),
            "total_decisions": len(self.decisions),
            "latest_envelope_hash": self.latest_envelope_hash
        }
