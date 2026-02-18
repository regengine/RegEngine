"""
Evidence Envelope V3 - Data Models
===================================
Cryptographic evidence with hash chaining and Merkle tree batching.

Key Features:
- Hash chaining (current_hash links to previous_hash)
- Merkle tree batching for integrity
- Tamper detection
- Chain continuity validation
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum


class EvidenceType(str, Enum):
    """Types of evidence."""
    DECISION = "decision"
    BIAS_REPORT = "bias_report"
    DRIFT_EVENT = "drift_event"
    MODEL_VALIDATION = "model_validation"
    OBLIGATION_EVALUATION = "obligation_evaluation"


class EvidenceEnvelopeV3(BaseModel):
    """
    Cryptographic evidence envelope with hash chaining and Merkle proof.
    
    Chain Structure:
    ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
    │  Envelope 1 │ ──> │  Envelope 2 │ ──> │  Envelope 3 │
    │  prev: null │     │  prev: E1   │     │  prev: E2   │
    │  hash: H1   │     │  hash: H2   │     │  hash: H3   │
    └─────────────┘     └─────────────┘     └─────────────┘
    """
    
    # Identity
    envelope_id: str = Field(..., description="Unique envelope ID (UUID)")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Hash Chain
    current_hash: str = Field(..., description="SHA-256 hash of evidence payload")
    previous_hash: Optional[str] = Field(None, description="Hash of previous envelope (null for chain root)")
    
    # Merkle Tree
    merkle_root: str = Field(..., description="Merkle root hash for batch integrity")
    merkle_proof: List[str] = Field(default_factory=list, description="Merkle proof path for verification")
    
    # Evidence Payload
    evidence_type: EvidenceType
    evidence_payload_hash: str = Field(..., description="Hash of the actual evidence content")
    evidence_payload: dict = Field(..., description="The evidence content itself")
    
    # Tamper Detection
    tamper_detected: bool = Field(default=False, description="Set to True if hash mismatch detected")


class MerkleNode(BaseModel):
    """Node in Merkle tree."""
    hash: str
    left_child: Optional['MerkleNode'] = None
    right_child: Optional['MerkleNode'] = None


class MerkleProof(BaseModel):
    """Merkle proof for verifying element in tree."""
    leaf_hash: str
    proof_path: List[str] = Field(..., description="Hashes needed to reconstruct root")
    root_hash: str


class VerificationRequest(BaseModel):
    """Request to verify evidence integrity."""
    envelope_id: str
    expected_payload: Optional[dict] = Field(None, description="Expected payload for tamper check")


class VerificationResult(BaseModel):
    """Result of evidence verification."""
    envelope_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Hash Verification
    hash_valid: bool = Field(..., description="Current hash matches recomputed hash")
    payload_hash_valid: bool = Field(..., description="Payload hash matches evidence content")
    
    # Chain Verification
    chain_valid: bool = Field(..., description="Previous hash matches predecessor's current hash")
    chain_length: int = Field(..., description="Number of envelopes in chain from this point to root")
    
    # Merkle Verification
    merkle_proof_valid: bool = Field(..., description="Merkle proof validates correctly")
    
    # Overall
    tamper_detected: bool = Field(..., description="Any integrity violation detected")
    verification_errors: List[str] = Field(default_factory=list)


class ChainStats(BaseModel):
    """Statistics about an evidence chain."""
    total_envelopes: int
    chain_root_id: str
    chain_head_id: str
    earliest_timestamp: datetime
    latest_timestamp: datetime
    evidence_types: dict  # Count of each evidence type
    all_hashes_valid: bool
