"""Evidence Service."""

from .envelope import (
    ChainStats,
    EvidenceEnvelopeV3,
    EvidenceType,
    MerkleNode,
    MerkleProof,
    VerificationRequest,
    VerificationResult,
)
from .hashing import compute_envelope_hash, compute_payload_hash, verify_hash
from .merkle import (
    append_to_chain,
    build_merkle_tree,
    compute_event_hash,
    generate_merkle_proof,
    verify_chain_integrity,
    verify_merkle_proof,
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
    "compute_event_hash",
    "append_to_chain",
    "verify_chain_integrity",
    "EvidenceVerifier",
]
