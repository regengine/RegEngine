"""Regression tests for issue #1313 — cte_persistence.hashing.

Before the fix, ``compute_idempotency_key`` called ``json.dumps(...,
sort_keys=True)`` with NO ``default=str``. A KDE containing a ``datetime``
or ``Decimal`` therefore raised ``TypeError`` mid-insert and lost the
event — in contrast to ``compute_event_hash`` which did have
``default=str`` and worked fine.

The fix (landed in #1465 / #1468) added ``default=str`` to match the
sister function. These tests lock in that behavior so a future refactor
can't silently reintroduce the TypeError, and verify the idempotency-key
semantics (deterministic, distinguishing) that downstream dedup relies on.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from services.shared.cte_persistence.hashing import (
    compute_chain_hash,
    compute_event_hash,
    compute_idempotency_key,
)


# ── #1313: no TypeError on datetime / Decimal KDEs ──────────────────────────


class TestComputeIdempotencyKeyNoTypeError_Issue1313:
    """Regression: #1313. The pre-fix code raised ``TypeError`` when a KDE
    value was a ``datetime`` or ``Decimal`` — losing the event. These
    tests fail immediately if ``default=str`` is ever removed again."""

    def test_datetime_in_kdes_does_not_raise(self):
        kdes = {
            "receipt_datetime": datetime(2026, 4, 18, 14, 30, tzinfo=timezone.utc),
            "lot_code": "ABC-123",
        }
        key = compute_idempotency_key(
            event_type="receiving",
            tlc="TLC-001",
            timestamp="2026-04-18T14:30:00Z",
            source="epcis",
            kdes=kdes,
        )
        assert isinstance(key, str)
        assert len(key) == 64  # sha256 hex

    def test_decimal_in_kdes_does_not_raise(self):
        kdes = {
            "quantity_decimal": Decimal("42.1234567890"),
            "price_usd": Decimal("3.50"),
        }
        key = compute_idempotency_key(
            event_type="shipping",
            tlc="TLC-002",
            timestamp="2026-04-18T14:30:00Z",
            source="edi",
            kdes=kdes,
        )
        assert isinstance(key, str)
        assert len(key) == 64

    def test_nested_datetime_and_decimal_does_not_raise(self):
        """Nested mix of exotic JSON types inside a single KDE value. Prior
        to #1313 this was another failure mode."""
        kdes = {
            "batch": {
                "produced_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "weight_kg": Decimal("1234.56"),
                "sublot": {
                    "sampled_on": date(2026, 1, 2),
                    "grams": Decimal("10.00"),
                },
            },
        }
        key = compute_idempotency_key(
            event_type="transformation",
            tlc="TLC-003",
            timestamp="2026-04-18T14:30:00Z",
            source="manual",
            kdes=kdes,
        )
        assert isinstance(key, str)

    def test_date_in_kdes_does_not_raise(self):
        kdes = {"harvest_date": date(2026, 4, 18)}
        key = compute_idempotency_key(
            event_type="growing",
            tlc="TLC-004",
            timestamp="2026-04-18T14:30:00Z",
            source="manual",
            kdes=kdes,
        )
        assert isinstance(key, str)

    def test_none_in_kdes_does_not_raise(self):
        """A common edge case — KDE explicitly ``None`` is valid JSON."""
        kdes = {"optional_lot_code": None, "text": "hello"}
        key = compute_idempotency_key(
            event_type="receiving",
            tlc="TLC-005",
            timestamp="2026-04-18T14:30:00Z",
            source="webhook",
            kdes=kdes,
        )
        assert isinstance(key, str)

    def test_empty_kdes_does_not_raise(self):
        key = compute_idempotency_key(
            event_type="receiving",
            tlc="TLC-006",
            timestamp="2026-04-18T14:30:00Z",
            source="manual",
            kdes={},
        )
        assert isinstance(key, str)


# ── Idempotency-key semantics (what dedup relies on) ────────────────────────


class TestComputeIdempotencyKeyDeterministic_Issue1313:
    def test_identical_inputs_yield_identical_key(self):
        kdes = {
            "a": Decimal("1.5"),
            "b": datetime(2026, 4, 18, tzinfo=timezone.utc),
        }
        k1 = compute_idempotency_key(
            event_type="receiving",
            tlc="TLC-X",
            timestamp="2026-04-18T00:00:00Z",
            source="epcis",
            kdes=kdes,
        )
        k2 = compute_idempotency_key(
            event_type="receiving",
            tlc="TLC-X",
            timestamp="2026-04-18T00:00:00Z",
            source="epcis",
            kdes=kdes,
        )
        assert k1 == k2

    def test_different_event_type_yields_different_key(self):
        k1 = compute_idempotency_key(
            event_type="receiving", tlc="TLC", timestamp="t", source="s", kdes={}
        )
        k2 = compute_idempotency_key(
            event_type="shipping", tlc="TLC", timestamp="t", source="s", kdes={}
        )
        assert k1 != k2

    def test_different_tlc_yields_different_key(self):
        k1 = compute_idempotency_key(
            event_type="receiving", tlc="TLC-A", timestamp="t", source="s", kdes={}
        )
        k2 = compute_idempotency_key(
            event_type="receiving", tlc="TLC-B", timestamp="t", source="s", kdes={}
        )
        assert k1 != k2

    def test_different_timestamp_yields_different_key(self):
        k1 = compute_idempotency_key(
            event_type="receiving", tlc="TLC", timestamp="2026-04-18", source="s", kdes={}
        )
        k2 = compute_idempotency_key(
            event_type="receiving", tlc="TLC", timestamp="2026-04-19", source="s", kdes={}
        )
        assert k1 != k2

    def test_different_source_yields_different_key(self):
        k1 = compute_idempotency_key(
            event_type="receiving", tlc="TLC", timestamp="t", source="epcis", kdes={}
        )
        k2 = compute_idempotency_key(
            event_type="receiving", tlc="TLC", timestamp="t", source="webhook", kdes={}
        )
        assert k1 != k2

    def test_different_location_gln_yields_different_key(self):
        """Location is part of event identity — FSMA 204 treats the same
        product shipped from two different warehouses at the same time as
        distinct events."""
        k1 = compute_idempotency_key(
            event_type="receiving",
            tlc="TLC",
            timestamp="t",
            source="s",
            kdes={},
            location_gln="GLN-A",
        )
        k2 = compute_idempotency_key(
            event_type="receiving",
            tlc="TLC",
            timestamp="t",
            source="s",
            kdes={},
            location_gln="GLN-B",
        )
        assert k1 != k2

    def test_different_kde_value_yields_different_key(self):
        k1 = compute_idempotency_key(
            event_type="r", tlc="T", timestamp="t", source="s", kdes={"x": 1},
        )
        k2 = compute_idempotency_key(
            event_type="r", tlc="T", timestamp="t", source="s", kdes={"x": 2},
        )
        assert k1 != k2

    def test_kde_key_order_does_not_affect_key(self):
        """``sort_keys=True`` must make key computation order-independent —
        critical because dict iteration order is insertion-ordered in
        Python 3.7+ and a reordered KDE payload must dedup."""
        k1 = compute_idempotency_key(
            event_type="r",
            tlc="T",
            timestamp="t",
            source="s",
            kdes={"a": 1, "b": 2, "c": 3},
        )
        k2 = compute_idempotency_key(
            event_type="r",
            tlc="T",
            timestamp="t",
            source="s",
            kdes={"c": 3, "a": 1, "b": 2},
        )
        assert k1 == k2


# ── Mirror check: compute_event_hash was already correct, lock it in ────────


class TestComputeEventHashExoticKDEs_Issue1313:
    def test_datetime_in_event_hash_kdes_does_not_raise(self):
        """``compute_event_hash`` had ``default=str`` all along — the
        inconsistency with ``compute_idempotency_key`` was the bug. Lock
        in that the sister function also still works."""
        h = compute_event_hash(
            event_id="evt-1",
            event_type="receiving",
            tlc="TLC",
            product_description="widgets",
            quantity=1.0,
            unit_of_measure="EA",
            location_gln=None,
            location_name=None,
            timestamp="2026-04-18",
            kdes={"delivered_at": datetime(2026, 4, 18, tzinfo=timezone.utc)},
        )
        assert isinstance(h, str)
        assert len(h) == 64

    def test_decimal_in_event_hash_kdes_does_not_raise(self):
        h = compute_event_hash(
            event_id="evt-2",
            event_type="shipping",
            tlc="TLC",
            product_description="widgets",
            quantity=2.0,
            unit_of_measure="EA",
            location_gln=None,
            location_name=None,
            timestamp="2026-04-18",
            kdes={"weight": Decimal("5.00")},
        )
        assert isinstance(h, str)


# ── Chain hash sanity (covered elsewhere but cheap to lock in) ──────────────


class TestComputeChainHash_Issue1313:
    def test_genesis_chain_hash_is_stable(self):
        h = compute_chain_hash("event-hash-1", None)
        assert h == compute_chain_hash("event-hash-1", None)

    def test_different_previous_chain_yields_different_result(self):
        h1 = compute_chain_hash("event-hash-1", "prev-1")
        h2 = compute_chain_hash("event-hash-1", "prev-2")
        assert h1 != h2
