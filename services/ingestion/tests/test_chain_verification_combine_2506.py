"""#2506 — the scheduled chain-verification job used only the legacy
``CTEPersistence.verify_chain``, which orphan-flags every chain row for a
canonical-only tenant (the canonical writer keys hash_chain rows to
``traceability_events.event_id``, not ``cte_events.id``).

The job now runs BOTH verifiers and combines them via
``_combine_verifications``: a chain row is a true orphan only if BOTH
stores miss it (legitimate during dual-write migration), while a
canonical event-content tamper or a sequence/linkage/chain_hash break is
a real failure regardless of store.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.chain_verification_job import _combine_verifications


def _canonical(valid, orphans=None, tamper=None, errors=None, length=0):
    return SimpleNamespace(
        valid=valid,
        chain_length=length,
        errors=errors or [],
        orphan_chain_rows=orphans or [],
        tamper_rows=tamper or [],
    )


def _legacy(valid, orphans=None, errors=None, length=0):
    return SimpleNamespace(
        valid=valid,
        chain_length=length,
        errors=errors or [],
        orphan_chain_rows=orphans or [],
    )


class TestCombineVerifications_Issue2506:
    def test_canonical_only_tenant_is_valid(self):
        """Canonical verifier passes; legacy orphan-flags every row. The
        combined verdict must be VALID — these are not true orphans."""
        canonical = _canonical(valid=True, length=3)
        legacy = _legacy(
            valid=False,
            orphans=[1, 2, 3],
            errors=["Orphan chain row at seq=1: ...", "Orphan chain row at seq=2: ..."],
            length=3,
        )
        valid, length, errors = _combine_verifications(canonical, legacy)
        assert valid is True
        assert length == 3
        assert errors == []

    def test_pure_legacy_tenant_is_valid(self):
        """Pure-legacy tenant (no canonical rows): canonical orphan-flags
        every row, legacy passes. Combined must be VALID."""
        canonical = _canonical(
            valid=False,
            orphans=[1, 2],
            errors=["Orphan chain row at seq=1: ...", "Orphan chain row at seq=2: ..."],
            length=2,
        )
        legacy = _legacy(valid=True, length=2)
        valid, length, errors = _combine_verifications(canonical, legacy)
        assert valid is True
        assert errors == []

    def test_true_orphan_in_both_stores_fails(self):
        canonical = _canonical(valid=False, orphans=[2], errors=["Orphan chain row at seq=2: ..."], length=3)
        legacy = _legacy(valid=False, orphans=[2], errors=["Orphan chain row at seq=2: ..."], length=3)
        valid, length, errors = _combine_verifications(canonical, legacy)
        assert valid is False
        assert any("BOTH stores" in e for e in errors)

    def test_canonical_event_tamper_always_fails(self):
        """A canonical event-content tamper is real even if the legacy
        verifier (which can't detect it) reports valid."""
        canonical = _canonical(
            valid=False,
            tamper=[2],
            errors=["Event tamper at seq=2: ..."],
            length=2,
        )
        legacy = _legacy(valid=True, length=2)
        valid, length, errors = _combine_verifications(canonical, legacy)
        assert valid is False
        assert any("Event tamper" in e for e in errors)

    def test_sequence_break_fails_even_if_legacy_valid(self):
        canonical = _canonical(
            valid=False,
            errors=["Sequence gap: expected 2, got 3"],
            length=2,
        )
        legacy = _legacy(valid=True, length=2)
        valid, _, errors = _combine_verifications(canonical, legacy)
        assert valid is False
        assert any("Sequence gap" in e for e in errors)

    def test_both_clean_is_valid(self):
        canonical = _canonical(valid=True, length=2)
        legacy = _legacy(valid=True, length=2)
        valid, length, errors = _combine_verifications(canonical, legacy)
        assert valid is True
        assert length == 2
        assert errors == []
