"""
Tests for kernel/evidence/merkle.py

Covers: Merkle tree construction, proof generation, proof verification,
and the hash-chain functions (compute_event_hash, append_to_chain,
verify_chain_integrity).
"""

import pytest
from kernel.evidence.merkle import (
    build_merkle_tree,
    generate_merkle_proof,
    verify_merkle_proof,
    hash_pair,
    compute_event_hash,
    append_to_chain,
    verify_chain_integrity,
)
from kernel.evidence.envelope import MerkleProof


# ─── build_merkle_tree ────────────────────────────────────────────────────────

class TestBuildMerkleTree:

    def test_single_element_root_equals_leaf(self):
        """With one leaf, the root hash is that leaf's hash (after duplication)."""
        leaf = "abc123leaf"
        root = build_merkle_tree([leaf])
        # Single leaf is duplicated → root = hash_pair(leaf, leaf)
        expected = hash_pair(leaf, leaf)
        assert root.hash == expected

    def test_two_elements_deterministic(self):
        """Two leaves produce the same root on repeated calls."""
        leaves = ["leaf_a", "leaf_b"]
        root1 = build_merkle_tree(leaves)
        root2 = build_merkle_tree(leaves)
        assert root1.hash == root2.hash

    def test_four_elements_deterministic(self):
        """Four leaves produce the same root on repeated calls."""
        leaves = ["h0", "h1", "h2", "h3"]
        root1 = build_merkle_tree(leaves)
        root2 = build_merkle_tree(leaves)
        assert root1.hash == root2.hash

    def test_eight_elements_deterministic(self):
        """Eight leaves produce the same root on repeated calls."""
        leaves = [f"hash_{i}" for i in range(8)]
        root1 = build_merkle_tree(leaves)
        root2 = build_merkle_tree(leaves)
        assert root1.hash == root2.hash

    def test_different_leaf_sets_produce_different_roots(self):
        """Different leaf sets must produce different roots."""
        leaves_a = ["a", "b", "c", "d"]
        leaves_b = ["a", "b", "c", "X"]  # one element changed
        root_a = build_merkle_tree(leaves_a)
        root_b = build_merkle_tree(leaves_b)
        assert root_a.hash != root_b.hash

    def test_empty_list_raises(self):
        """Empty leaf list must raise ValueError."""
        with pytest.raises(ValueError):
            build_merkle_tree([])

    def test_odd_number_of_leaves_handled(self):
        """Odd number of leaves (e.g. 3, 5) is handled via duplication."""
        leaves = ["h0", "h1", "h2"]
        root = build_merkle_tree(leaves)
        assert root.hash is not None
        assert len(root.hash) == 64  # SHA-256 hex digest

    def test_root_hash_is_64_char_hex(self):
        """Root hash is a valid SHA-256 hex digest (64 chars)."""
        root = build_merkle_tree(["leaf1", "leaf2"])
        assert len(root.hash) == 64
        int(root.hash, 16)  # must be valid hex — raises ValueError if not


# ─── generate_merkle_proof ────────────────────────────────────────────────────

class TestGenerateMerkleProof:

    def test_proof_for_leaf_0_in_4_leaf_tree(self):
        """Proof for leaf 0 in a 4-leaf tree has the right path length."""
        leaves = ["h0", "h1", "h2", "h3"]
        proof = generate_merkle_proof(leaves, 0)
        # A balanced 4-leaf tree has depth 2, so proof path has 2 sibling hashes.
        assert len(proof.proof_path) == 2

    def test_proof_contains_leaf_hash(self):
        """Proof.leaf_hash matches the leaf at that index."""
        leaves = ["alpha", "beta", "gamma", "delta"]
        for i, leaf in enumerate(leaves):
            proof = generate_merkle_proof(leaves, i)
            assert proof.leaf_hash == leaf

    def test_proof_root_matches_tree_root(self):
        """Proof.root_hash matches the root of the full tree."""
        leaves = ["h0", "h1", "h2", "h3"]
        tree_root = build_merkle_tree(leaves)
        for i in range(len(leaves)):
            proof = generate_merkle_proof(leaves, i)
            assert proof.root_hash == tree_root.hash

    def test_out_of_range_index_raises(self):
        """Index out of range raises ValueError."""
        with pytest.raises(ValueError):
            generate_merkle_proof(["a", "b"], 5)

    def test_negative_index_raises(self):
        """Negative index raises ValueError."""
        with pytest.raises(ValueError):
            generate_merkle_proof(["a", "b"], -1)


# ─── verify_merkle_proof ──────────────────────────────────────────────────────

class TestVerifyMerkleProof:

    def test_valid_proof_returns_true(self):
        """Round-trip: generate proof then verify it returns True."""
        leaves = ["leaf0", "leaf1", "leaf2", "leaf3"]
        for i in range(len(leaves)):
            proof = generate_merkle_proof(leaves, i)
            assert verify_merkle_proof(proof) is True

    def test_valid_proof_8_leaves(self):
        """Valid proof round-trip works for 8 leaves."""
        leaves = [f"h{i}" for i in range(8)]
        for i in range(len(leaves)):
            proof = generate_merkle_proof(leaves, i)
            assert verify_merkle_proof(proof) is True

    def test_tampered_leaf_hash_fails(self):
        """Changing proof.leaf_hash makes verification return False."""
        leaves = ["a", "b", "c", "d"]
        proof = generate_merkle_proof(leaves, 0)
        tampered = MerkleProof(
            leaf_hash="tampered_hash",
            proof_path=proof.proof_path,
            root_hash=proof.root_hash,
        )
        assert verify_merkle_proof(tampered) is False

    def test_tampered_proof_path_fails(self):
        """Changing a node in proof_path makes verification return False."""
        leaves = ["a", "b", "c", "d"]
        proof = generate_merkle_proof(leaves, 0)
        bad_path = list(proof.proof_path)
        bad_path[0] = "bad_sibling_hash"
        tampered = MerkleProof(
            leaf_hash=proof.leaf_hash,
            proof_path=bad_path,
            root_hash=proof.root_hash,
        )
        assert verify_merkle_proof(tampered) is False

    def test_wrong_root_hash_fails(self):
        """A valid proof against the wrong root hash returns False."""
        leaves = ["a", "b", "c", "d"]
        proof = generate_merkle_proof(leaves, 0)
        tampered = MerkleProof(
            leaf_hash=proof.leaf_hash,
            proof_path=proof.proof_path,
            root_hash="completely_wrong_root",
        )
        assert verify_merkle_proof(tampered) is False


# ─── compute_event_hash ───────────────────────────────────────────────────────

class TestComputeEventHash:

    def _make_event(self, **overrides):
        base = {
            "event_id": "evt-001",
            "event_type": "SHIPPING",
            "tlc": "TLC-XYZ-9999",
            "timestamp": "2026-01-01T00:00:00Z",
            "previous_hash": None,
        }
        base.update(overrides)
        return base

    def test_returns_64_char_hex_string(self):
        """Hash is a 64-char SHA-256 hex digest."""
        h = compute_event_hash(self._make_event())
        assert len(h) == 64
        int(h, 16)  # valid hex

    def test_deterministic_same_inputs(self):
        """Same inputs always produce the same hash."""
        event = self._make_event()
        assert compute_event_hash(event) == compute_event_hash(event)

    def test_different_event_id_changes_hash(self):
        """Changing event_id changes the hash."""
        h1 = compute_event_hash(self._make_event(event_id="evt-001"))
        h2 = compute_event_hash(self._make_event(event_id="evt-002"))
        assert h1 != h2

    def test_different_event_type_changes_hash(self):
        h1 = compute_event_hash(self._make_event(event_type="SHIPPING"))
        h2 = compute_event_hash(self._make_event(event_type="RECEIVING"))
        assert h1 != h2

    def test_different_tlc_changes_hash(self):
        h1 = compute_event_hash(self._make_event(tlc="TLC-A"))
        h2 = compute_event_hash(self._make_event(tlc="TLC-B"))
        assert h1 != h2

    def test_different_previous_hash_changes_hash(self):
        """Chain linkage: changing previous_hash changes this event's hash."""
        h1 = compute_event_hash(self._make_event(previous_hash=None))
        h2 = compute_event_hash(self._make_event(previous_hash="some-prev-hash"))
        assert h1 != h2

    def test_extra_fields_ignored(self):
        """Extra non-canonical fields do not affect the hash."""
        event_base = self._make_event()
        event_extra = dict(event_base, extra_field="should be ignored")
        assert compute_event_hash(event_base) == compute_event_hash(event_extra)


# ─── verify_chain_integrity ───────────────────────────────────────────────────

class TestVerifyChainIntegrity:

    def _build_chain(self, n: int):
        """Build a valid chain of n events using append_to_chain."""
        chain = []
        prev_hash = None
        for i in range(n):
            event = {
                "event_id": f"evt-{i:03d}",
                "event_type": "SHIPPING",
                "tlc": f"TLC-{i:04d}",
                "timestamp": f"2026-01-01T00:{i:02d}:00Z",
            }
            chained = append_to_chain(event, prev_hash)
            chain.append(chained)
            prev_hash = chained["_next_merkle_hash"]
        return chain

    def test_empty_chain_is_valid(self):
        result = verify_chain_integrity([])
        assert result["valid"] is True
        assert result["length"] == 0
        assert result["errors"] == []

    def test_single_event_chain_is_valid(self):
        chain = self._build_chain(1)
        result = verify_chain_integrity(chain)
        assert result["valid"] is True
        assert result["length"] == 1

    def test_multi_event_chain_is_valid(self):
        chain = self._build_chain(5)
        result = verify_chain_integrity(chain)
        assert result["valid"] is True
        assert result["length"] == 5

    def test_tampered_event_field_detected(self):
        """Modifying a field in an event breaks the stored hash."""
        chain = self._build_chain(3)
        # Tamper with event 1's tlc without recomputing the hash
        chain[1] = dict(chain[1], tlc="TAMPERED-TLC")
        result = verify_chain_integrity(chain)
        assert result["valid"] is False
        assert any(e["index"] == 1 for e in result["errors"])

    def test_broken_chain_link_detected(self):
        """Setting previous_hash to a wrong value breaks chain linkage."""
        chain = self._build_chain(3)
        # Break the link between event 1 and event 2
        chain[2] = dict(chain[2], previous_hash="wrong-previous-hash")
        result = verify_chain_integrity(chain)
        assert result["valid"] is False
        assert any(
            e.get("issue") in ("hash_mismatch", "chain_link_broken")
            for e in result["errors"]
        )

    def test_genesis_with_previous_hash_detected(self):
        """Genesis event (index 0) must have previous_hash == None."""
        chain = self._build_chain(2)
        # Give the genesis a non-None previous_hash
        chain[0] = dict(chain[0], previous_hash="unexpected-predecessor")
        result = verify_chain_integrity(chain)
        assert result["valid"] is False
        assert any(e.get("issue") == "genesis_has_previous_hash" for e in result["errors"])
