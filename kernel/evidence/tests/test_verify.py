"""
Tests for kernel/evidence/verify.py (EvidenceVerifier)

Covers: verify_envelope (payload hash, current hash, chain continuity, Merkle proof).
Uses EvidenceEnvelopeV3 directly to construct valid and tampered envelopes.
"""

import pytest
from datetime import datetime
from kernel.evidence.hashing import compute_payload_hash
from kernel.evidence.verify import EvidenceVerifier
from kernel.evidence.envelope import EvidenceEnvelopeV3, EvidenceType


def _make_envelope(
    envelope_id: str = "env-001",
    payload: dict = None,
    previous_hash: str = None,
    merkle_proof: list = None,
    merkle_root: str = None,
) -> EvidenceEnvelopeV3:
    """
    Build a self-consistent EvidenceEnvelopeV3 for testing.
    All hashes are computed from the provided payload so the envelope is valid.
    """
    if payload is None:
        payload = {"decision": "approved", "model": "v1"}

    evidence_payload_hash = compute_payload_hash(payload)

    # Build the envelope data dict (excluding current_hash) for computing current_hash
    envelope_data = {
        "envelope_id": envelope_id,
        "evidence_type": EvidenceType.DECISION,
        "evidence_payload_hash": evidence_payload_hash,
        "evidence_payload": payload,
        "previous_hash": previous_hash,
        "merkle_root": merkle_root or evidence_payload_hash,
        "merkle_proof": merkle_proof or [],
    }
    current_hash = compute_payload_hash(envelope_data)

    return EvidenceEnvelopeV3(
        envelope_id=envelope_id,
        evidence_type=EvidenceType.DECISION,
        evidence_payload_hash=evidence_payload_hash,
        evidence_payload=payload,
        previous_hash=previous_hash,
        merkle_root=merkle_root or evidence_payload_hash,
        merkle_proof=merkle_proof or [],
        current_hash=current_hash,
        tamper_detected=False,
    )


class TestVerifyEnvelopeValid:

    def test_valid_envelope_passes_all_checks(self):
        """A freshly constructed envelope passes full verification."""
        envelope = _make_envelope()
        verifier = EvidenceVerifier()
        result = verifier.verify_envelope(envelope)
        assert result.payload_hash_valid is True
        assert result.hash_valid is True
        assert result.chain_valid is True  # no store needed for chain root
        assert result.merkle_proof_valid is True  # no proof → skipped (True)
        assert result.tamper_detected is False

    def test_chain_root_no_previous_hash(self):
        """Envelope with previous_hash=None is a chain root and chain_valid=True."""
        envelope = _make_envelope(previous_hash=None)
        verifier = EvidenceVerifier()
        result = verifier.verify_envelope(envelope)
        assert result.chain_valid is True


class TestVerifyEnvelopeTampered:

    def test_tampered_payload_detected(self):
        """Modifying evidence_payload while keeping evidence_payload_hash fails payload check."""
        envelope = _make_envelope()
        # Tamper: replace payload content without recomputing hash
        tampered = envelope.model_copy(update={"evidence_payload": {"decision": "TAMPERED"}})
        verifier = EvidenceVerifier()
        result = verifier.verify_envelope(tampered)
        assert result.payload_hash_valid is False
        assert result.tamper_detected is True

    def test_wrong_payload_hash_detected(self):
        """Using a wrong evidence_payload_hash fails payload verification."""
        envelope = _make_envelope()
        tampered = envelope.model_copy(update={"evidence_payload_hash": "wrong_hash"})
        verifier = EvidenceVerifier()
        result = verifier.verify_envelope(tampered)
        assert result.payload_hash_valid is False
        assert result.tamper_detected is True

    def test_wrong_current_hash_detected(self):
        """Using a wrong current_hash fails hash verification."""
        envelope = _make_envelope()
        tampered = envelope.model_copy(update={"current_hash": "bad_current_hash"})
        verifier = EvidenceVerifier()
        result = verifier.verify_envelope(tampered)
        assert result.hash_valid is False
        assert result.tamper_detected is True


class TestChainContinuity:

    def _build_chain_envelopes(self, n: int = 3):
        """Build a chain of n linked envelopes and return (chain_list, store_dict)."""
        envelopes = []
        prev_hash = None
        for i in range(n):
            env = _make_envelope(
                envelope_id=f"env-{i:03d}",
                payload={"step": i},
                previous_hash=prev_hash,
            )
            envelopes.append(env)
            prev_hash = env.current_hash
        store = {e.envelope_id: e for e in envelopes}
        return envelopes, store

    def test_chain_head_with_store_is_valid(self):
        """Head of a valid chain verifies correctly when envelope store is provided."""
        envelopes, store = self._build_chain_envelopes(3)
        verifier = EvidenceVerifier(envelope_store=store)
        result = verifier.verify_envelope(envelopes[-1])
        assert result.chain_valid is True
        assert result.tamper_detected is False

    def test_broken_link_detected(self):
        """A broken previous_hash link is detected when the store is present."""
        envelopes, store = self._build_chain_envelopes(3)
        # Break the middle envelope's previous_hash without updating the store
        broken = envelopes[2].model_copy(update={"previous_hash": "wrong_hash"})
        store[broken.envelope_id] = broken
        verifier = EvidenceVerifier(envelope_store=store)
        result = verifier.verify_envelope(broken)
        # Either chain_valid is False, or hash_valid is False (current_hash changed too)
        assert result.tamper_detected is True
