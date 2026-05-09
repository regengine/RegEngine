"""
Tests for kernel/evidence/hashing.py

Covers: compute_payload_hash, compute_envelope_hash, verify_hash.
"""

import pytest
from kernel.evidence.hashing import (
    compute_payload_hash,
    compute_envelope_hash,
    verify_hash,
)


class TestComputePayloadHash:

    def test_returns_64_char_hex_string(self):
        """SHA-256 hex digest is exactly 64 characters."""
        h = compute_payload_hash({"key": "value"})
        assert len(h) == 64
        int(h, 16)  # raises ValueError if not valid hex

    def test_same_inputs_produce_same_hash(self):
        """Function is deterministic."""
        payload = {"a": 1, "b": "hello", "c": [1, 2, 3]}
        assert compute_payload_hash(payload) == compute_payload_hash(payload)

    def test_key_order_does_not_matter(self):
        """Canonical JSON sorts keys, so ordering must not affect the hash."""
        p1 = {"z": 1, "a": 2}
        p2 = {"a": 2, "z": 1}
        assert compute_payload_hash(p1) == compute_payload_hash(p2)

    def test_changing_value_changes_hash(self):
        """Modifying any field changes the hash."""
        original = {"amount": 100, "currency": "USD"}
        tampered = {"amount": 999, "currency": "USD"}
        assert compute_payload_hash(original) != compute_payload_hash(tampered)

    def test_adding_field_changes_hash(self):
        """Adding a field changes the hash."""
        original = {"a": 1}
        extended = {"a": 1, "b": 2}
        assert compute_payload_hash(original) != compute_payload_hash(extended)

    def test_empty_dict_produces_consistent_hash(self):
        """Empty dict produces the same hash every time."""
        h1 = compute_payload_hash({})
        h2 = compute_payload_hash({})
        assert h1 == h2
        assert len(h1) == 64

    def test_nested_dict_hashed_correctly(self):
        """Nested structures are hashed consistently."""
        payload = {"outer": {"inner": "value"}}
        h1 = compute_payload_hash(payload)
        h2 = compute_payload_hash(payload)
        assert h1 == h2

    def test_different_types_produce_different_hashes(self):
        """String '1' vs integer 1 produce different hashes."""
        h_int = compute_payload_hash({"v": 1})
        h_str = compute_payload_hash({"v": "1"})
        assert h_int != h_str


class TestComputeEnvelopeHash:

    def test_excludes_current_hash_field(self):
        """current_hash is excluded from the hash computation (no circular dep)."""
        envelope_without = {"payload": "data", "timestamp": "2026-01-01T00:00:00Z"}
        envelope_with = dict(envelope_without, current_hash="some-existing-hash")
        # Both should hash to the same value since current_hash is stripped
        assert compute_envelope_hash(envelope_without) == compute_envelope_hash(envelope_with)

    def test_excludes_tamper_detected_field(self):
        """tamper_detected is excluded from the hash computation."""
        envelope_clean = {"payload": "data"}
        envelope_flagged = dict(envelope_clean, tamper_detected=True)
        assert compute_envelope_hash(envelope_clean) == compute_envelope_hash(envelope_flagged)

    def test_other_fields_affect_hash(self):
        """Changing non-excluded fields changes the hash."""
        e1 = {"payload": "original", "timestamp": "2026-01-01"}
        e2 = {"payload": "tampered", "timestamp": "2026-01-01"}
        assert compute_envelope_hash(e1) != compute_envelope_hash(e2)


class TestVerifyHash:

    def test_correct_hash_returns_true(self):
        payload = {"status": "approved", "score": 0.95}
        correct_hash = compute_payload_hash(payload)
        assert verify_hash(payload, correct_hash) is True

    def test_wrong_hash_returns_false(self):
        payload = {"status": "approved"}
        assert verify_hash(payload, "definitely_wrong_hash") is False

    def test_tampered_payload_returns_false(self):
        original = {"amount": 100}
        correct_hash = compute_payload_hash(original)
        tampered = {"amount": 999}
        assert verify_hash(tampered, correct_hash) is False
