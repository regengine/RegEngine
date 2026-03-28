"""
Merkle Tree for CTE Hash Chain Verification.

Provides O(log n) inclusion proofs and efficient root-hash verification
for the FSMA 204 hash chain, complementing the existing linear chain
verification in cte_persistence.py.

Usage:
    from services.shared.merkle_tree import MerkleTree

    tree = MerkleTree(event_hashes)
    root = tree.root
    proof = tree.generate_proof(index)
    valid = MerkleTree.verify_proof(event_hash, proof, root)
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import List, Optional


def _hash_pair(left: str, right: str) -> str:
    """Hash two hex-encoded SHA-256 digests together, sorted for canonical ordering."""
    combined = f"{left}|{right}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def _hash_leaf(event_hash: str) -> str:
    """Hash a leaf node with a domain-separation prefix to prevent second-preimage attacks."""
    return hashlib.sha256(f"leaf|{event_hash}".encode("utf-8")).hexdigest()


@dataclass
class MerkleProofStep:
    """A single step in a Merkle inclusion proof."""
    position: str  # "left" or "right" — sibling's position relative to the path node
    hash: str

    def to_dict(self) -> dict:
        return {"position": self.position, "hash": self.hash}

    @classmethod
    def from_dict(cls, d: dict) -> MerkleProofStep:
        return cls(position=d["position"], hash=d["hash"])


class MerkleTree:
    """
    Binary Merkle tree built from a list of event hashes.

    The tree is computed entirely in memory. Leaf nodes are domain-separated
    (prefixed with "leaf|") to prevent second-preimage attacks. Internal
    nodes concatenate children with "|" separator, matching the existing
    compute_chain_hash convention.

    If the number of leaves is not a power of two, the last leaf is
    duplicated to fill the tree (standard Merkle padding).
    """

    def __init__(self, hashes: list[str]):
        if not hashes:
            self._layers: list[list[str]] = []
            self._root: str = hashlib.sha256(b"empty").hexdigest()
            self._leaf_count = 0
            return

        self._leaf_count = len(hashes)

        # Build leaf layer with domain separation
        leaves = [_hash_leaf(h) for h in hashes]

        # Pad to even count by duplicating last leaf
        if len(leaves) % 2 == 1 and len(leaves) > 1:
            leaves.append(leaves[-1])

        self._layers = [leaves]
        self._build()

    def _build(self) -> None:
        """Build internal layers bottom-up until we reach the root."""
        current = self._layers[0]
        while len(current) > 1:
            next_layer = []
            for i in range(0, len(current), 2):
                if i + 1 < len(current):
                    next_layer.append(_hash_pair(current[i], current[i + 1]))
                else:
                    # Odd node — promote (duplicate)
                    next_layer.append(_hash_pair(current[i], current[i]))
            self._layers.append(next_layer)
            current = next_layer
        self._root = current[0]

    @property
    def root(self) -> str:
        """The Merkle root hash."""
        return self._root

    @property
    def depth(self) -> int:
        """Tree depth (number of layers minus 1, i.e. edges from root to leaf)."""
        if not self._layers:
            return 0
        return len(self._layers) - 1

    @property
    def leaf_count(self) -> int:
        """Number of original (non-padded) leaves."""
        return self._leaf_count

    def generate_proof(self, index: int) -> list[dict]:
        """
        Generate an inclusion proof for the leaf at the given index.

        Returns a list of proof steps, each with 'position' and 'hash'.
        The position indicates whether the sibling is to the 'left' or 'right'
        of the path node at that level.
        """
        if not self._layers or index < 0 or index >= self._leaf_count:
            raise IndexError(f"Index {index} out of range [0, {self._leaf_count})")

        proof: list[dict] = []
        idx = index

        # Adjust for padding: if odd leaf count and index is within padded layer
        for layer in self._layers[:-1]:  # skip root layer
            if idx % 2 == 0:
                # Sibling is to the right
                sibling_idx = idx + 1
                if sibling_idx < len(layer):
                    proof.append({"position": "right", "hash": layer[sibling_idx]})
                else:
                    # No sibling (shouldn't happen after padding, but defensive)
                    proof.append({"position": "right", "hash": layer[idx]})
            else:
                # Sibling is to the left
                sibling_idx = idx - 1
                proof.append({"position": "left", "hash": layer[sibling_idx]})

            idx = idx // 2

        return proof

    @staticmethod
    def verify_proof(event_hash: str, proof: list[dict], root: str) -> bool:
        """
        Verify that an event_hash is included in a tree with the given root.

        Args:
            event_hash: The original event hash (before leaf hashing).
            proof: List of proof steps from generate_proof().
            root: The expected Merkle root.

        Returns:
            True if the proof is valid and the event is in the tree.
        """
        current = _hash_leaf(event_hash)

        for step in proof:
            sibling = step["hash"]
            if step["position"] == "right":
                current = _hash_pair(current, sibling)
            else:
                current = _hash_pair(sibling, current)

        return current == root


# ---------------------------------------------------------------------------
# Convenience functions (module-level API)
# ---------------------------------------------------------------------------

def compute_merkle_root(hashes: list[str]) -> str:
    """Compute the Merkle root from a list of event hashes."""
    tree = MerkleTree(hashes)
    return tree.root


def generate_proof(hashes: list[str], index: int) -> list[dict]:
    """Generate an inclusion proof for a specific event by index."""
    tree = MerkleTree(hashes)
    return tree.generate_proof(index)


def verify_proof(event_hash: str, proof: list[dict], root: str) -> bool:
    """Verify an inclusion proof against a Merkle root."""
    return MerkleTree.verify_proof(event_hash, proof, root)
