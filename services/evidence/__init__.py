"""Evidence Service."""

from .envelope import (
    EvidenceEnvelopeV3,
    EvidenceType,
    MerkleNode,
    MerkleProof,
    VerificationRequest,
    VerificationResult,
    ChainStats
)
from .hashing import compute_payload_hash, compute_envelope_hash, verify_hash
from .merkle import (
    build_merkle_tree,
    generate_merkle_proof,
    verify_merkle_proof
)
from .verify import EvidenceVerifier

__all__ = [
    "EvidenceEnvelopeV3",
    "EvidenceType",
    "MerkleNode",
    "MerkleProof",
    "VerificationRequest",
    "VerificationResult",
    "ChainStats",
    "compute_payload_hash",
    "compute_envelope_hash",
    "verify_hash",
    "build_merkle_tree",
    "generate_merkle_proof",
    "verify_merkle_proof",
    "EvidenceVerifier"
]
