"""Tests for shared.cte_persistence.hashing helpers.

Primary focus: the #1313 regression — ``compute_idempotency_key``
was missing ``default=str`` in its ``json.dumps`` call, causing any
KDE carrying a ``datetime`` or ``Decimal`` to raise ``TypeError``
mid-insert and lose the event.

These tests are pure-Python and require no DB.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from shared.cte_persistence.hashing import (
    compute_event_hash,
    compute_idempotency_key,
)


BASE_KEY_ARGS: dict = {
    "event_type": "shipping",
    "tlc": "TLC-1",
    "timestamp": "2026-04-18T00:00:00+00:00",
    "source": "webhook",
    "location_gln": "0614141000005",
    "location_name": "Facility A",
}


class TestComputeIdempotencyKey_Issue1313:
    def test_datetime_kde_does_not_raise(self):
        """Pre-fix: raised TypeError on json.dumps(datetime)."""
        kdes = {"last_updated_at": datetime(2026, 4, 18, tzinfo=timezone.utc)}
        # Must not raise
        key = compute_idempotency_key(**BASE_KEY_ARGS, kdes=kdes)
        assert isinstance(key, str) and len(key) == 64  # sha256 hex

    def test_decimal_kde_does_not_raise(self):
        """Pre-fix: raised TypeError on json.dumps(Decimal)."""
        kdes = {"quantity": Decimal("10.5"), "net_weight": Decimal("1234.56")}
        key = compute_idempotency_key(**BASE_KEY_ARGS, kdes=kdes)
        assert isinstance(key, str) and len(key) == 64

    def test_mixed_non_jsonable_kdes(self):
        """Mixture of datetime + Decimal + standard primitives."""
        kdes = {
            "quantity": Decimal("42"),
            "harvested_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "gtin": "09506000134352",
            "organic": True,
        }
        key = compute_idempotency_key(**BASE_KEY_ARGS, kdes=kdes)
        assert isinstance(key, str) and len(key) == 64

    def test_stable_across_python_key_insertion_order(self):
        """Changing dict insertion order must not change the key
        (``sort_keys=True`` guarantees this)."""
        k1 = compute_idempotency_key(
            **BASE_KEY_ARGS, kdes={"a": 1, "b": Decimal("2")}
        )
        k2 = compute_idempotency_key(
            **BASE_KEY_ARGS, kdes={"b": Decimal("2"), "a": 1}
        )
        assert k1 == k2, "key must be order-independent"

    def test_matches_compute_event_hash_behaviour_for_datetime(self):
        """compute_event_hash already tolerates datetime via default=str.
        compute_idempotency_key now matches."""
        ts = datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc)
        event_args = dict(
            event_id="evt-1",
            event_type="shipping",
            tlc="TLC-1",
            product_description="apples",
            quantity=10.0,
            unit_of_measure="kg",
            location_gln="0614141000005",
            location_name="Facility A",
            timestamp="2026-04-18T00:00:00+00:00",
            kdes={"recorded_at": ts},
        )
        # Neither helper should raise.
        compute_event_hash(**event_args)
        compute_idempotency_key(
            **BASE_KEY_ARGS, kdes={"recorded_at": ts}
        )

    def test_explicit_isoformat_normalization_not_str_coercion(self):
        """The hashing path now uses an explicit type-dispatch normalizer
        (``_normalize_for_hashing``) that maps ``datetime`` →
        ``isoformat()`` rather than relying on ``json.dumps(default=str)``.
        This makes the serialization contract a code-owned invariant that
        survives Python interpreter upgrades — a silent change to
        ``datetime.__str__`` can no longer invalidate every idempotency
        key mid-deploy. See #1313.

        Previously this test asserted ``str(dt) == key-input``; it is now
        flipped to assert ``isoformat()`` is the canonical form, and that
        ``str(dt)`` is NOT (they differ: ``str`` uses a space separator,
        ``isoformat`` uses ``"T"``).
        """
        ts = datetime(2026, 4, 18, tzinfo=timezone.utc)
        key_with_dt = compute_idempotency_key(
            **BASE_KEY_ARGS, kdes={"t": ts}
        )
        # After #1313's explicit normalization, the datetime is serialized
        # via ``isoformat()`` — so passing the ISO-string explicitly must
        # reproduce the same key.
        key_with_iso = compute_idempotency_key(
            **BASE_KEY_ARGS, kdes={"t": ts.isoformat()}
        )
        assert key_with_dt == key_with_iso, (
            "datetime KDE must normalize to isoformat() under the new "
            "explicit type-dispatch in _normalize_for_hashing"
        )
        # And passing ``str(dt)`` (which uses a space separator) must NOT
        # produce the same key — guards against accidental regression to
        # ``default=str``.
        key_with_str = compute_idempotency_key(
            **BASE_KEY_ARGS, kdes={"t": str(ts)}
        )
        assert key_with_dt != key_with_str, (
            "str(datetime) uses a space separator and must no longer be "
            "the canonical form; if this passes, _normalize_for_hashing "
            "has regressed to default=str"
        )
