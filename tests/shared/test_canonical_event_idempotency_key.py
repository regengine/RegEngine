"""Tests for ``TraceabilityEvent.compute_idempotency_key`` — canonical-side
mirror of the #1313 regression guard.

Before the fix: canonical_event.TraceabilityEvent.compute_idempotency_key
called ``json.dumps(..., sort_keys=True, separators=(",", ":"))`` with no
``default=str``. A KDE carrying a ``datetime`` or ``Decimal`` raised
``TypeError`` mid-insert and lost the event — the same bug class as
#1313 on the CTE-side formula, but silently present on the canonical
path too.

After the fix: ``default=str`` is added, matching
``shared.cte_persistence.hashing.compute_idempotency_key`` (fixed in
PR-A) and ``compute_event_hash`` (which has had ``default=str`` since
inception).

Pure-Python; no DB.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from shared.canonical_event import (
    CTEType,
    EventStatus,
    IngestionSource,
    ProvenanceMetadata,
    TraceabilityEvent,
)


def _make_canonical_event(kdes: dict) -> TraceabilityEvent:
    return TraceabilityEvent(
        event_id=uuid4(),
        tenant_id=uuid4(),
        source_system=IngestionSource.WEBHOOK_API,
        source_record_id="rec-1",
        event_type=CTEType.SHIPPING,
        event_timestamp=datetime(2026, 4, 18, tzinfo=timezone.utc),
        event_timezone="UTC",
        product_reference="urn:gs1:01:09506000134352",
        lot_reference="LOT-1",
        traceability_lot_code="TLC-1",
        quantity=10.0,
        unit_of_measure="kg",
        from_entity_reference="urn:gs1:417:0614141000005",
        to_entity_reference="urn:gs1:417:0614141000012",
        from_facility_reference="urn:gs1:414:0614141000005",
        to_facility_reference="urn:gs1:414:0614141000012",
        kdes=kdes,
        raw_payload={},
        normalized_payload={},
        provenance_metadata=ProvenanceMetadata(),
        confidence_score=1.0,
        status=EventStatus.ACTIVE,
    )


class TestCanonicalIdempotencyKey_Issue1313Mirror:
    def test_datetime_kde_does_not_raise(self):
        evt = _make_canonical_event(
            {"last_updated_at": datetime(2026, 4, 18, tzinfo=timezone.utc)}
        )
        key = evt.compute_idempotency_key()
        assert isinstance(key, str) and len(key) == 64

    def test_decimal_kde_does_not_raise(self):
        evt = _make_canonical_event(
            {"quantity": Decimal("10.5"), "net_weight": Decimal("1234.56")}
        )
        key = evt.compute_idempotency_key()
        assert isinstance(key, str) and len(key) == 64

    def test_mixed_non_jsonable_kdes(self):
        evt = _make_canonical_event({
            "quantity": Decimal("42"),
            "harvested_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "gtin": "09506000134352",
            "organic": True,
        })
        key = evt.compute_idempotency_key()
        assert isinstance(key, str) and len(key) == 64

    def test_stable_across_kde_insertion_order(self):
        e1 = _make_canonical_event({"a": 1, "b": Decimal("2")})
        e2 = _make_canonical_event({"b": Decimal("2"), "a": 1})
        # Same tenants / ids will produce the same key even though the
        # instances differ — only content-addressable fields feed the
        # hash, and ``sort_keys=True`` + ``default=str`` make the
        # serialization deterministic.
        # (event_id / tenant_id differ between the two; compute_idempotency_key
        # does not include them, so equality holds.)
        assert e1.compute_idempotency_key() == e2.compute_idempotency_key()

    def test_key_diverges_from_cte_formula_documented(self):
        """Documents the intentional formula divergence: the canonical
        formula uses from_facility/to_facility while the CTE formula
        uses location_gln/location_name. Cross-table reconciliation by
        idempotency_key is NOT supported; use sha256_hash instead."""
        from shared.cte_persistence.hashing import compute_idempotency_key

        kdes = {"ship_date": "2026-04-18"}
        canonical_evt = _make_canonical_event(kdes)
        canonical_key = canonical_evt.compute_idempotency_key()

        cte_key = compute_idempotency_key(
            event_type=canonical_evt.event_type.value,
            tlc=canonical_evt.traceability_lot_code,
            timestamp=canonical_evt.event_timestamp.isoformat(),
            source=canonical_evt.source_system.value,
            kdes=kdes,
            # Use GLN/name; the CTE formula hashes these, not facility refs.
            location_gln="0614141000005",
            location_name="Facility A",
        )

        # They should NOT match — this is the intentional divergence
        # documented in both modules' docstrings.
        assert canonical_key != cte_key, (
            "If this test starts passing equality, the formulas have drifted "
            "into convergence — update docstrings and the reconciliation note"
        )
