"""Regression tests for issue #1323.

``product_description`` must NOT participate in the event hash.  It is a
mutable, human-readable field (subject to translation, reformatting, and
vendor normalisation).  Including it caused re-ingestion of the same
physical event with a reformatted description to produce a different
SHA-256 hash, breaking both idempotency dedup and hash-chain verification.

The fix (already landed) excludes ``product_description`` from the
canonical string while retaining it in the function signature for
backward-compatibility.

These tests lock the behaviour so a future refactor cannot silently add
the field back.
"""

from __future__ import annotations

import pytest

from services.shared.cte_persistence.hashing import compute_event_hash

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_BASE = dict(
    event_id="evt-001",
    event_type="receiving",
    tlc="TLC-XYZ",
    product_description="Fresh Roma Tomatoes",
    quantity=100.0,
    unit_of_measure="cases",
    location_gln="0614141000005",
    location_name="Warehouse A",
    timestamp="2026-04-20T10:00:00Z",
    kdes={"lot_code": "LOT-99"},
)


# ---------------------------------------------------------------------------
# Core regression: description changes must NOT change the hash
# ---------------------------------------------------------------------------


class TestProductDescriptionExcludedFromHash:
    def test_different_descriptions_produce_identical_hash(self):
        """Same event, different product_description → same SHA-256 hash."""
        hash_a = compute_event_hash(**{**_BASE, "product_description": "Fresh Roma Tomatoes"})
        hash_b = compute_event_hash(**{**_BASE, "product_description": "Tomates fraîches Roma"})
        hash_c = compute_event_hash(**{**_BASE, "product_description": "FRESH ROMA TOMATOES (ORGANIC)"})

        assert hash_a == hash_b == hash_c, (
            "product_description must not influence the event hash (#1323) — "
            "reformatted descriptions must hash identically"
        )

    def test_empty_description_same_hash(self):
        """Callers that pass an empty string get the same hash."""
        hash_a = compute_event_hash(**{**_BASE, "product_description": "Fresh Roma Tomatoes"})
        hash_b = compute_event_hash(**{**_BASE, "product_description": ""})
        assert hash_a == hash_b

    def test_whitespace_only_description_same_hash(self):
        hash_a = compute_event_hash(**_BASE)
        hash_b = compute_event_hash(**{**_BASE, "product_description": "   \t\n   "})
        assert hash_a == hash_b


# ---------------------------------------------------------------------------
# Stable identifiers DO change the hash
# ---------------------------------------------------------------------------


class TestStableFieldsStillAffectHash:
    """Confirm the non-mutable fields are still part of the hash.  If these
    pass, the hash is not a constant (i.e., the function is not broken)."""

    def test_different_event_id_different_hash(self):
        h1 = compute_event_hash(**_BASE)
        h2 = compute_event_hash(**{**_BASE, "event_id": "evt-002"})
        assert h1 != h2

    def test_different_tlc_different_hash(self):
        h1 = compute_event_hash(**_BASE)
        h2 = compute_event_hash(**{**_BASE, "tlc": "TLC-OTHER"})
        assert h1 != h2

    def test_different_quantity_different_hash(self):
        h1 = compute_event_hash(**_BASE)
        h2 = compute_event_hash(**{**_BASE, "quantity": 999.0})
        assert h1 != h2

    def test_different_kdes_different_hash(self):
        h1 = compute_event_hash(**_BASE)
        h2 = compute_event_hash(**{**_BASE, "kdes": {"lot_code": "DIFFERENT"}})
        assert h1 != h2


# ---------------------------------------------------------------------------
# Hash stability / determinism
# ---------------------------------------------------------------------------


class TestHashDeterminism:
    def test_same_inputs_always_same_hash(self):
        hashes = [compute_event_hash(**_BASE) for _ in range(10)]
        assert len(set(hashes)) == 1, "compute_event_hash must be deterministic"

    def test_hash_is_64_char_hex(self):
        h = compute_event_hash(**_BASE)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)
