"""
Merkle Tree Module
==================
Merkle tree construction and proof generation for batch integrity.

Merkle trees allow efficient verification that a specific piece of evidence
is part of a larger batch without revealing the entire batch.
"""

import hashlib
from typing import List, Tuple, Optional
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
