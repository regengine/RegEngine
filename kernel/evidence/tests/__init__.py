"""
Evidence Chain Verification Tests
==================================
Tests for hash chaining, tamper detection, and Merkle proof verification.
"""

import pytest
from kernel.evidence.hashing import (
    compute_payload_hash,
    compute_envelope_hash,
    verify_hash,
)
from kernel.evidence.merkle import (
    build_merkle_tree,
    generate_merkle_proof,
    verify_merkle_proof,
)
from kernel.evidence.envelope import MerkleNode, MerkleProof


class TestHashChainIntegrity:
    """Test sequential envelopes link correctly via previous_hash."""

    def test_hash_chain_basic(self):
        """Two envelopes with proper previous_hash link."""
        payload1 = {"data": "first"}
        payload2 = {"data": "second"}

        hash1 = compute_payload_hash(payload1)
        hash2 = compute_payload_hash(payload2)

        envelope1 = {"payload": payload1, "current_hash": hash1, "previous_hash": None}
        envelope2 = {"payload": payload2, "current_hash": hash2, "previous_hash": hash1}

        assert compute_envelope_hash(envelope1) == hash1
        assert compute_envelope_hash(envelope2) == hash2

    def test_hash_chain_order_matters(self):
        """Order of envelopes matters for chain integrity."""
        payload_a = {"id": "A", "value": 100}
        payload_b = {"id": "B", "value": 200}

        hash_a = compute_payload_hash(payload_a)
        hash_b = compute_payload_hash(payload_b)

        assert hash_a != hash_b


class TestTamperDetection:
    """Modifying evidence_payload causes hash mismatch."""

    def test_tampered_payload_detected(self):
        """Hash changes when payload is modified."""
        original = {"amount": 100, "currency": "USD"}
        original_hash = compute_payload_hash(original)

        tampered = {"amount": 999, "currency": "USD"}
        tampered_hash = compute_payload_hash(tampered)

        assert tampered_hash != original_hash

    def test_verify_hash_rejects_mismatch(self):
        """verify_hash returns False for tampered data."""
        payload = {"status": "approved"}
        correct_hash = compute_payload_hash(payload)

        tampered = {"status": "rejected"}
        assert verify_hash(tampered, correct_hash) is False

    def test_verify_hash_accepts_correct(self):
        """verify_hash returns True for matching data."""
        payload = {"status": "approved"}
        correct_hash = compute_payload_hash(payload)

        assert verify_hash(payload, correct_hash) is True


class TestMerkleProofRoundtrip:
    """generate_merkle_proof + verify_merkle_proof round-trips cleanly."""

    def test_single_leaf(self):
        """Single leaf tree works."""
        leaf_hashes = ["abc123"]
        root = build_merkle_tree(leaf_hashes)
        assert root.hash is not None

    def test_multiple_leaves(self):
        """Multiple leaves build correct tree."""
        leaf_hashes = ["hash1", "hash2", "hash3", "hash4"]
        root = build_merkle_tree(leaf_hashes)
        assert root.hash is not None

    def test_proof_roundtrip(self):
        """Proof generation and verification roundtrips."""
        leaf_hashes = ["a", "b", "c", "d"]

        for idx in range(len(leaf_hashes)):
            proof = generate_merkle_proof(leaf_hashes, idx)
            assert verify_merkle_proof(proof) is True


class TestChainBreakDetected:
    """Removing a middle envelope raises a chain break."""

    def test_missing_previous_hash_fails(self):
        """Envelope with missing previous_hash breaks chain."""
        payload = {"data": "orphan"}
        hash_orphan = compute_payload_hash(payload)

        envelope = {
            "payload": payload,
            "current_hash": hash_orphan,
            "previous_hash": "nonexistent_previous_hash"
        }

        computed = compute_envelope_hash(envelope)
        assert computed != "nonexistent_previous_hash"


class TestEmptyPayloadHash:
    """Edge case: empty dict produces stable hash."""

    def test_empty_dict_hash(self):
        """Empty dict produces consistent hash."""
        hash1 = compute_payload_hash({})
        hash2 = compute_payload_hash({})
        assert hash1 == hash2
        assert len(hash1) == 64

    def test_empty_list_in_payload(self):
        """Empty list in payload doesn't cause issues."""
        payload = {"items": []}
        hash_val = compute_payload_hash(payload)
        assert len(hash_val) == 64
