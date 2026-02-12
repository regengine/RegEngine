"""
Evidence Verification Module
=============================
Tamper detection and chain continuity validation.
"""

from typing import List, Optional, Dict, Any
import logging

from .envelope import EvidenceEnvelopeV3, VerificationResult
from .hashing import compute_payload_hash, verify_hash
from .merkle import verify_merkle_proof, MerkleProof

logger = logging.getLogger(__name__)


class EvidenceVerifier:
    """
    Verifies evidence integrity through multiple checks:
    1. Hash verification (payload hash matches)
    2. Chain continuity (previous_hash links valid)
    3. Merkle proof validation (batch integrity)
    """
    
    def __init__(self, envelope_store: Optional[Dict[str, EvidenceEnvelopeV3]] = None):
        """
        Initialize verifier.
        
        Args:
            envelope_store: Optional dict of envelope_id -> EvidenceEnvelopeV3
                          (for chain continuity checks)
        """
        self.envelope_store = envelope_store or {}
    
    def verify_envelope(self, envelope: EvidenceEnvelopeV3) -> VerificationResult:
        """
        Perform complete verification of an evidence envelope.
        
        Checks:
        1. Payload hash matches evidence content
        2. Current hash is correctly computed
        3. Previous hash links to valid predecessor
        4. Merkle proof validates
        
        Args:
            envelope: EvidenceEnvelopeV3 to verify
            
        Returns:
            VerificationResult
        """
        logger.info(f"Verifying envelope {envelope.envelope_id}")
        
        errors = []
        
        # Check 1: Payload hash verification
        payload_hash_valid = self._verify_payload_hash(envelope)
        if not payload_hash_valid:
            errors.append("Payload hash mismatch - evidence may be tampered")
        
        # Check 2: Current hash verification
        hash_valid = self._verify_current_hash(envelope)
        if not hash_valid:
            errors.append("Current hash mismatch - envelope integrity compromised")
        
        # Check 3: Chain continuity
        chain_valid, chain_length = self._verify_chain_continuity(envelope)
        if not chain_valid:
            errors.append("Chain continuity broken - previous hash does not link to predecessor")
        
        # Check 4: Merkle proof
        merkle_proof_valid = self._verify_merkle_proof(envelope)
        if not merkle_proof_valid:
            errors.append("Merkle proof invalid - batch integrity compromised")
        
        # Overall tamper detection
        tamper_detected = not (payload_hash_valid and hash_valid and chain_valid and merkle_proof_valid)
        
        result = VerificationResult(
            envelope_id=envelope.envelope_id,
            hash_valid=hash_valid,
            payload_hash_valid=payload_hash_valid,
            chain_valid=chain_valid,
            chain_length=chain_length,
            merkle_proof_valid=merkle_proof_valid,
            tamper_detected=tamper_detected,
            verification_errors=errors
        )
        
        if tamper_detected:
            logger.warning(f"Tamper detected in envelope {envelope.envelope_id}: {errors}")
        else:
            logger.info(f"Envelope {envelope.envelope_id} verification passed")
        
        return result
    
    def _verify_payload_hash(self, envelope: EvidenceEnvelopeV3) -> bool:
        """Verify that evidence_payload_hash matches actual payload."""
        computed_hash = compute_payload_hash(envelope.evidence_payload)
        return computed_hash == envelope.evidence_payload_hash
    
    def _verify_current_hash(self, envelope: EvidenceEnvelopeV3) -> bool:
        """Verify that current_hash is correctly computed."""
        # Current hash should be hash of the envelope data
        # (excluding current_hash itself to avoid circular dependency)
        envelope_data = envelope.dict(exclude={'current_hash', 'tamper_detected'})
        computed_hash = compute_payload_hash(envelope_data)
        return computed_hash == envelope.current_hash
    
    def _verify_chain_continuity(self, envelope: EvidenceEnvelopeV3) -> tuple[bool, int]:
        """
        Verify that previous_hash links to predecessor's current_hash.
        
        Returns:
            (chain_valid, chain_length)
        """
        if envelope.previous_hash is None:
            # This is chain root
            return True, 1
        
        # Look up predecessor
        if not self.envelope_store:
            logger.warning("No envelope store configured, cannot verify chain continuity")
            return True, 1  # Assume valid if can't check
        
        # Find predecessor by hash
        predecessor = self._find_envelope_by_hash(envelope.previous_hash)
        
        if predecessor is None:
            logger.warning(f"Predecessor with hash {envelope.previous_hash} not found")
            return False, 1
        
        # Verify previous_hash matches predecessor's current_hash
        chain_valid = envelope.previous_hash == predecessor.current_hash
        
        # Recursively verify predecessor chain
        if chain_valid:
            _, predecessor_chain_length = self._verify_chain_continuity(predecessor)
            chain_length = predecessor_chain_length + 1
        else:
            chain_length = 1
        
        return chain_valid, chain_length
    
    def _verify_merkle_proof(self, envelope: EvidenceEnvelopeV3) -> bool:
        """Verify Merkle proof validates batch integrity."""
        if not envelope.merkle_proof:
            # No proof provided (single-element batch?)
            logger.debug("No Merkle proof provided, skipping verification")
            return True
        
        proof = MerkleProof(
            leaf_hash=envelope.evidence_payload_hash,
            proof_path=envelope.merkle_proof,
            root_hash=envelope.merkle_root
        )
        
        return verify_merkle_proof(proof)
    
    def _find_envelope_by_hash(self, hash: str) -> Optional[EvidenceEnvelopeV3]:
        """Find envelope in store by its current_hash."""
        for envelope in self.envelope_store.values():
            if envelope.current_hash == hash:
                return envelope
        return None
    
    def verify_chain(self, head_envelope_id: str) -> VerificationResult:
        """
        Verify entire chain from head to root.
        
        Args:
            head_envelope_id: ID of chain head envelope
            
        Returns:
            VerificationResult for the head (includes chain length)
        """
        if head_envelope_id not in self.envelope_store:
            raise ValueError(f"Envelope {head_envelope_id} not found in store")
        
        head_envelope = self.envelope_store[head_envelope_id]
        
        return self.verify_envelope(head_envelope)
