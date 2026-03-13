"""
Merkle Tree Module
==================
Merkle tree construction and proof generation for batch integrity.

Merkle trees allow efficient verification that a specific piece of evidence
is part of a larger batch without revealing the entire batch.

Also provides SupplierCTEEvent hash-chaining functions for ISO 27001
tamper-evident logging of FSMA 204 critical tracking events.
"""

import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple
from .envelope import MerkleNode, MerkleProof


def hash_pair(left: str, right: str) -> str:
    """
    Hash a pair of hashes together.
    
    Args:
        left: Left hash
        right: Right hash
        
    Returns:
        Combined hash
    """
    combined = (left + right).encode('utf-8')
    return hashlib.sha256(combined).hexdigest()


def build_merkle_tree(leaf_hashes: List[str]) -> MerkleNode:
    """
    Build a Merkle tree from leaf hashes.
    
    Args:
        leaf_hashes: List of leaf node hashes
        
    Returns:
        Root MerkleNode
    """
    if not leaf_hashes:
        raise ValueError("Cannot build Merkle tree from empty list")
    
    # Create leaf nodes
    current_level = [MerkleNode(hash=h) for h in leaf_hashes]
    
    # If odd number of leaves, duplicate last one
    if len(current_level) % 2 == 1:
        current_level.append(current_level[-1])
    
    # Build tree bottom-up
    while len(current_level) > 1:
        next_level = []
        
        for i in range(0, len(current_level), 2):
            left = current_level[i]
            right = current_level[i + 1] if i + 1 < len(current_level) else left
            
            parent_hash = hash_pair(left.hash, right.hash)
            parent = MerkleNode(hash=parent_hash, left_child=left, right_child=right)
            
            next_level.append(parent)
        
        # If odd number at this level, duplicate last
        if len(next_level) % 2 == 1 and len(next_level) > 1:
            next_level.append(next_level[-1])
        
        current_level = next_level
    
    return current_level[0]


def generate_merkle_proof(leaf_hashes: List[str], leaf_index: int) -> MerkleProof:
    """
    Generate Merkle proof for a specific leaf.
    
    Args:
        leaf_hashes: All leaf hashes in tree
        leaf_index: Index of leaf to prove
        
    Returns:
        MerkleProof
    """
    if leaf_index < 0 or leaf_index >= len(leaf_hashes):
        raise ValueError(f"Leaf index {leaf_index} out of range")
    
    root = build_merkle_tree(leaf_hashes)
    leaf_hash = leaf_hashes[leaf_index]
    
    # Generate proof path
    proof_path = _generate_proof_path(leaf_hashes, leaf_index)
    
    return MerkleProof(
        leaf_hash=leaf_hash,
        proof_path=proof_path,
        root_hash=root.hash
    )


def _generate_proof_path(leaf_hashes: List[str], leaf_index: int) -> List[str]:
    """
    Generate proof path (sibling hashes needed to reconstruct root).
    
    Args:
        leaf_hashes: All leaf hashes
        leaf_index: Index of target leaf
        
    Returns:
        List of sibling hashes
    """
    proof_path = []
    current_level = leaf_hashes.copy()
    current_index = leaf_index
    
    # Handle odd number of leaves
    if len(current_level) % 2 == 1:
        current_level.append(current_level[-1])
    
    while len(current_level) > 1:
        # Get sibling index
        if current_index % 2 == 0:
            sibling_index = current_index + 1
        else:
            sibling_index = current_index - 1
        
        # Add sibling to proof path
        if sibling_index < len(current_level):
            proof_path.append(current_level[sibling_index])
        
        # Move to parent level
        next_level = []
        for i in range(0, len(current_level), 2):
            left = current_level[i]
            right = current_level[i + 1] if i + 1 < len(current_level) else left
            parent_hash = hash_pair(left, right)
            next_level.append(parent_hash)
        
        # Handle odd number at parent level
        if len(next_level) % 2 == 1 and len(next_level) > 1:
            next_level.append(next_level[-1])
        
        current_level = next_level
        current_index = current_index // 2
    
    return proof_path


# =============================================================================
# SupplierCTEEvent Hash-Chain Functions (ISO 27001 Tamper-Evident Logging)
# =============================================================================


def compute_event_hash(event_data: Dict[str, Any]) -> str:
    """
    Compute a deterministic SHA-256 hash for a SupplierCTEEvent record.

    The hash covers the canonical fields that define a CTE event's identity:
    event_id, event_type, tlc, timestamp, and previous_hash. This ensures
    that any modification to these fields is cryptographically detectable.

    Args:
        event_data: Dict containing at minimum:
            - event_id: Unique event identifier
            - event_type: CTE type (SHIPPING, RECEIVING, CREATION, etc.)
            - tlc: Traceability Lot Code
            - timestamp: ISO-8601 timestamp string
            - previous_hash: Hash of the preceding event (None for genesis)

    Returns:
        SHA-256 hex digest of the canonical event representation
    """
    canonical = {
        "event_id": event_data.get("event_id", ""),
        "event_type": event_data.get("event_type", ""),
        "tlc": event_data.get("tlc", ""),
        "timestamp": event_data.get("timestamp", ""),
        "previous_hash": event_data.get("previous_hash"),
    }
    canonical_json = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def append_to_chain(
    event: Dict[str, Any],
    previous_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Append a SupplierCTEEvent to a hash chain.

    Sets the ``previous_hash`` field on the event, computes the event's own
    hash, and stores it as ``_next_merkle_hash`` so the next event can
    reference it.  Returns a *new* dict (the original is not mutated).

    Args:
        event: Dict with event_id, event_type, tlc, timestamp fields.
        previous_hash: The ``_next_merkle_hash`` of the preceding event in
            the chain.  ``None`` for the genesis (first) event.

    Returns:
        A copy of the event dict augmented with:
            - previous_hash: the provided predecessor hash
            - _next_merkle_hash: this event's computed hash (to be
              referenced by the next event)
    """
    chained = dict(event)
    chained["previous_hash"] = previous_hash
    event_hash = compute_event_hash(chained)
    chained["_next_merkle_hash"] = event_hash
    return chained


def verify_chain_integrity(chain: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Walk a list of SupplierCTEEvent dicts and verify hash-chain integrity.

    Each event's ``_next_merkle_hash`` must equal the recomputed hash of its
    canonical fields, and each event's ``previous_hash`` must equal the
    preceding event's ``_next_merkle_hash``.

    Args:
        chain: Ordered list of event dicts (oldest first).

    Returns:
        Dict with:
            - valid (bool): True if the entire chain is intact.
            - length (int): Number of events in the chain.
            - errors (list[dict]): Details of each detected violation,
              each containing ``index``, ``event_id``, and ``issue``.
    """
    errors: List[Dict[str, Any]] = []

    if not chain:
        return {"valid": True, "length": 0, "errors": []}

    for i, event in enumerate(chain):
        event_id = event.get("event_id", f"<index {i}>")

        # 1. Verify the stored hash matches a fresh recomputation.
        expected_hash = compute_event_hash(event)
        stored_hash = event.get("_next_merkle_hash")
        if stored_hash != expected_hash:
            errors.append({
                "index": i,
                "event_id": event_id,
                "issue": "hash_mismatch",
                "expected": expected_hash,
                "stored": stored_hash,
            })

        # 2. Verify chain linkage: previous_hash must reference predecessor.
        if i == 0:
            # Genesis event must have previous_hash == None.
            if event.get("previous_hash") is not None:
                errors.append({
                    "index": i,
                    "event_id": event_id,
                    "issue": "genesis_has_previous_hash",
                    "found": event.get("previous_hash"),
                })
        else:
            predecessor = chain[i - 1]
            expected_prev = predecessor.get("_next_merkle_hash")
            actual_prev = event.get("previous_hash")
            if actual_prev != expected_prev:
                errors.append({
                    "index": i,
                    "event_id": event_id,
                    "issue": "chain_link_broken",
                    "expected_previous": expected_prev,
                    "actual_previous": actual_prev,
                })

    return {
        "valid": len(errors) == 0,
        "length": len(chain),
        "errors": errors,
    }


def verify_merkle_proof(proof: MerkleProof) -> bool:
    """
    Verify a Merkle proof.
    
    Reconstructs root hash from leaf and proof path,
    then compares with expected root.
    
    Args:
        proof: MerkleProof to verify
        
    Returns:
        True if proof is valid
    """
    current_hash = proof.leaf_hash
    
    for sibling_hash in proof.proof_path:
        # Combine with sibling (order matters for determinism)
        # Use lexicographic order to ensure consistency
        if current_hash < sibling_hash:
            current_hash = hash_pair(current_hash, sibling_hash)
        else:
            current_hash = hash_pair(sibling_hash, current_hash)
    
    return current_hash == proof.root_hash
