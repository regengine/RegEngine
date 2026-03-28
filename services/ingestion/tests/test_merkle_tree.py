"""Unit tests for the Merkle tree module (services/shared/merkle_tree.py)."""

import sys
from pathlib import Path

_ingestion_dir = Path(__file__).resolve().parent.parent
if str(_ingestion_dir) not in sys.path:
    sys.path.insert(0, str(_ingestion_dir))

_services_dir = _ingestion_dir.parent
if str(_services_dir) not in sys.path:
    sys.path.insert(0, str(_services_dir))

import hashlib
import pytest

from shared.merkle_tree import MerkleTree, compute_merkle_root, generate_proof, verify_proof


class TestComputeMerkleRoot:
    """Test compute_merkle_root with various list sizes."""

    def test_single_hash(self):
        hashes = ["aaa111"]
        root = compute_merkle_root(hashes)
        assert isinstance(root, str)
        assert len(root) == 64  # SHA-256 hex digest

    def test_two_hashes(self):
        root = compute_merkle_root(["aaa", "bbb"])
        assert len(root) == 64

    def test_three_hashes(self):
        root = compute_merkle_root(["aaa", "bbb", "ccc"])
        assert len(root) == 64

    def test_four_hashes(self):
        root = compute_merkle_root(["a", "b", "c", "d"])
        assert len(root) == 64

    def test_seven_hashes(self):
        hashes = [f"hash_{i}" for i in range(7)]
        root = compute_merkle_root(hashes)
        assert len(root) == 64

    def test_hundred_hashes(self):
        hashes = [hashlib.sha256(f"event_{i}".encode()).hexdigest() for i in range(100)]
        root = compute_merkle_root(hashes)
        assert len(root) == 64

    def test_deterministic_same_input_same_root(self):
        hashes = ["abc", "def", "ghi"]
        root1 = compute_merkle_root(hashes)
        root2 = compute_merkle_root(hashes)
        assert root1 == root2

    def test_different_input_different_root(self):
        root1 = compute_merkle_root(["abc", "def"])
        root2 = compute_merkle_root(["abc", "xyz"])
        assert root1 != root2

    def test_empty_input(self):
        root = compute_merkle_root([])
        # Empty tree still returns a deterministic root
        assert isinstance(root, str)
        assert len(root) == 64
        expected = hashlib.sha256(b"empty").hexdigest()
        assert root == expected


class TestGenerateAndVerifyProof:
    """Test generate_proof + verify_proof round-trip."""

    def test_roundtrip_single_leaf(self):
        hashes = ["only_leaf"]
        tree = MerkleTree(hashes)
        proof = tree.generate_proof(0)
        assert verify_proof("only_leaf", proof, tree.root) is True

    def test_roundtrip_two_leaves(self):
        hashes = ["leaf_0", "leaf_1"]
        tree = MerkleTree(hashes)
        for i in range(len(hashes)):
            proof = tree.generate_proof(i)
            assert verify_proof(hashes[i], proof, tree.root) is True

    def test_roundtrip_three_leaves(self):
        hashes = ["a", "b", "c"]
        tree = MerkleTree(hashes)
        for i in range(len(hashes)):
            proof = tree.generate_proof(i)
            assert verify_proof(hashes[i], proof, tree.root) is True

    def test_roundtrip_four_leaves(self):
        hashes = ["w", "x", "y", "z"]
        tree = MerkleTree(hashes)
        for i in range(len(hashes)):
            proof = tree.generate_proof(i)
            assert verify_proof(hashes[i], proof, tree.root) is True

    def test_roundtrip_seven_leaves(self):
        hashes = [f"event_{i}" for i in range(7)]
        tree = MerkleTree(hashes)
        for i in range(len(hashes)):
            proof = tree.generate_proof(i)
            assert verify_proof(hashes[i], proof, tree.root) is True

    def test_roundtrip_large_tree(self):
        hashes = [hashlib.sha256(f"e{i}".encode()).hexdigest() for i in range(50)]
        tree = MerkleTree(hashes)
        for i in range(len(hashes)):
            proof = tree.generate_proof(i)
            assert verify_proof(hashes[i], proof, tree.root) is True

    def test_convenience_functions_roundtrip(self):
        """Test the module-level convenience functions."""
        hashes = ["alpha", "beta", "gamma", "delta"]
        root = compute_merkle_root(hashes)
        for i in range(len(hashes)):
            proof = generate_proof(hashes, i)
            assert verify_proof(hashes[i], proof, root) is True


class TestVerifyProofRejectsTampering:
    """Test that verify_proof rejects tampered data."""

    def _build_tree_and_proof(self):
        hashes = ["aaa", "bbb", "ccc", "ddd"]
        tree = MerkleTree(hashes)
        proof = tree.generate_proof(0)
        return hashes, tree, proof

    def test_rejects_tampered_event_hash(self):
        hashes, tree, proof = self._build_tree_and_proof()
        # Use a different event hash than the one the proof was generated for
        assert verify_proof("TAMPERED", proof, tree.root) is False

    def test_rejects_tampered_proof_step(self):
        hashes, tree, proof = self._build_tree_and_proof()
        assert len(proof) > 0
        # Tamper with the hash in the first proof step
        tampered_proof = [dict(s) for s in proof]
        tampered_proof[0]["hash"] = "0" * 64
        assert verify_proof(hashes[0], tampered_proof, tree.root) is False

    def test_rejects_wrong_root(self):
        hashes, tree, proof = self._build_tree_and_proof()
        wrong_root = "f" * 64
        assert verify_proof(hashes[0], proof, wrong_root) is False


class TestMerkleTreeEdgeCases:
    """Edge cases and property tests."""

    def test_empty_tree_depth(self):
        tree = MerkleTree([])
        assert tree.depth == 0
        assert tree.leaf_count == 0

    def test_generate_proof_out_of_range(self):
        tree = MerkleTree(["a", "b"])
        with pytest.raises(IndexError):
            tree.generate_proof(2)
        with pytest.raises(IndexError):
            tree.generate_proof(-1)

    def test_generate_proof_empty_tree(self):
        tree = MerkleTree([])
        with pytest.raises(IndexError):
            tree.generate_proof(0)

    def test_leaf_count_matches_input(self):
        for n in [1, 2, 3, 4, 7, 15, 16]:
            hashes = [f"h{i}" for i in range(n)]
            tree = MerkleTree(hashes)
            assert tree.leaf_count == n

    def test_proof_step_serialization(self):
        from shared.merkle_tree import MerkleProofStep
        step = MerkleProofStep(position="left", hash="abc123")
        d = step.to_dict()
        assert d == {"position": "left", "hash": "abc123"}
        restored = MerkleProofStep.from_dict(d)
        assert restored.position == "left"
        assert restored.hash == "abc123"
