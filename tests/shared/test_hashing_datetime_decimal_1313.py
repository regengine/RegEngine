"""Regression tests for issue #1313 — explicit type normalization in
shared.cte_persistence.hashing.

Problem (pre-fix): ``compute_idempotency_key`` called
``json.dumps(..., sort_keys=True)`` with no ``default=`` argument. A KDE
carrying a ``datetime`` or ``Decimal`` therefore raised ``TypeError``
mid-insert and the event was lost. The sister function ``compute_event_hash``
had ``default=str``, which avoided the TypeError but was version/locale-
fragile — ``str(datetime)``'s format is not a stable API contract and a
silent Python upgrade could change every idempotency key and event hash,
breaking dedup across deploys.

Fix: ``_normalize_for_hashing`` is an explicit type-dispatch that converts
``datetime``/``date`` → ``isoformat()``, ``Decimal`` → fixed-point string
(``format(..., 'f')``), and ``UUID`` → ``str``. It recurses into dicts
and lists. Both ``compute_idempotency_key`` and ``compute_event_hash``
now share this normalization path — no more ``default=str``.

These tests are pure-Python and require no DB.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from shared.cte_persistence.hashing import (
    _normalize_for_hashing,
    compute_event_hash,
    compute_idempotency_key,
)


BASE_KEY_ARGS: dict = {
    "event_type": "shipping",
    "tlc": "TLC-1",
    "timestamp": "2026-04-20T00:00:00+00:00",
    "source": "webhook",
    "location_gln": "0614141000005",
    "location_name": "Facility A",
}


BASE_EVENT_ARGS: dict = {
    "event_id": "evt-1",
    "event_type": "shipping",
    "tlc": "TLC-1",
    "product_description": "Lettuce",
    "quantity": 1.0,
    "unit_of_measure": "kg",
    "location_gln": None,
    "location_name": None,
    "timestamp": "2026-04-20T00:00:00+00:00",
}


# =============================================================================
# Pre-fix crash regression — neither function may raise on exotic KDEs
# =============================================================================


class TestComputeIdempotencyKeyDoesNotRaise:
    """Pre-fix: raised TypeError mid-insert on exotic types."""

    def test_datetime_kde_does_not_raise(self):
        kdes = {"receipt_datetime": datetime(2026, 4, 20, 14, 30, tzinfo=timezone.utc)}
        key = compute_idempotency_key(**BASE_KEY_ARGS, kdes=kdes)
        assert isinstance(key, str)
        assert len(key) == 64  # sha256 hex

    def test_decimal_kde_does_not_raise(self):
        kdes = {"quantity_decimal": Decimal("42.1234567890")}
        key = compute_idempotency_key(**BASE_KEY_ARGS, kdes=kdes)
        assert isinstance(key, str)
        assert len(key) == 64

    def test_date_kde_does_not_raise(self):
        kdes = {"harvest_date": date(2026, 4, 20)}
        key = compute_idempotency_key(**BASE_KEY_ARGS, kdes=kdes)
        assert isinstance(key, str)

    def test_uuid_kde_does_not_raise(self):
        kdes = {"correlation_id": UUID("00000000-0000-0000-0000-00000000cafe")}
        key = compute_idempotency_key(**BASE_KEY_ARGS, kdes=kdes)
        assert isinstance(key, str)

    def test_nested_exotic_types_do_not_raise(self):
        """Nested mix of exotic types in a single KDE — the normalizer
        must recurse into dicts and lists."""
        kdes = {
            "batch": {
                "produced_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "weight_kg": Decimal("1234.56"),
                "sublots": [
                    {"sampled_on": date(2026, 1, 2), "grams": Decimal("10.00")},
                    {"sampled_on": date(2026, 1, 3), "grams": Decimal("11.00")},
                ],
            },
        }
        key = compute_idempotency_key(**BASE_KEY_ARGS, kdes=kdes)
        assert isinstance(key, str)


class TestComputeEventHashDoesNotRaise:
    """Mirror: ``compute_event_hash`` shares the same normalizer now
    and must also tolerate the full set of exotic types."""

    def test_datetime_kde_does_not_raise(self):
        h = compute_event_hash(
            **BASE_EVENT_ARGS,
            kdes={"delivered_at": datetime(2026, 4, 20, tzinfo=timezone.utc)},
        )
        assert isinstance(h, str) and len(h) == 64

    def test_decimal_kde_does_not_raise(self):
        h = compute_event_hash(
            **BASE_EVENT_ARGS, kdes={"weight": Decimal("5.00")},
        )
        assert isinstance(h, str)

    def test_uuid_kde_does_not_raise(self):
        h = compute_event_hash(
            **BASE_EVENT_ARGS,
            kdes={"correlation_id": UUID("00000000-0000-0000-0000-00000000beef")},
        )
        assert isinstance(h, str)


# =============================================================================
# Stability — equal-value but distinct objects must hash equal
# =============================================================================


class TestStabilityAcrossEqualButDistinctObjects:
    """The whole point of the normalizer: two calls with inputs that are
    value-equal but object-distinct must produce the same key. Dedup
    across ingestion paths depends on this (two parsers constructing
    their own datetime objects for the same event must dedup)."""

    def test_datetime_two_distinct_but_equal_objects_yield_same_key(self):
        dt_a = datetime(2026, 4, 20, 0, 0, 0, tzinfo=timezone.utc)
        dt_b = datetime(2026, 4, 20, 0, 0, 0, tzinfo=timezone.utc)
        assert dt_a is not dt_b  # sanity: two different objects
        assert dt_a == dt_b  # sanity: value-equal

        k1 = compute_idempotency_key(
            **BASE_KEY_ARGS, kdes={"t": dt_a}
        )
        k2 = compute_idempotency_key(
            **BASE_KEY_ARGS, kdes={"t": dt_b}
        )
        assert k1 == k2

    def test_decimal_two_distinct_but_equal_objects_yield_same_key(self):
        d_a = Decimal("42.0")
        d_b = Decimal("42.0")
        assert d_a is not d_b
        assert d_a == d_b

        k1 = compute_idempotency_key(
            **BASE_KEY_ARGS, kdes={"q": d_a}
        )
        k2 = compute_idempotency_key(
            **BASE_KEY_ARGS, kdes={"q": d_b}
        )
        assert k1 == k2

    def test_compute_event_hash_stability(self):
        dt_a = datetime(2026, 4, 20, tzinfo=timezone.utc)
        dt_b = datetime(2026, 4, 20, tzinfo=timezone.utc)
        h1 = compute_event_hash(**BASE_EVENT_ARGS, kdes={"t": dt_a})
        h2 = compute_event_hash(**BASE_EVENT_ARGS, kdes={"t": dt_b})
        assert h1 == h2


# =============================================================================
# Canonical form — ISO-offset is the canonical form chosen
# =============================================================================


class TestCanonicalDatetimeForm:
    """The normalizer pins the canonical datetime form to ``isoformat()``.
    Callers that pre-convert to that form must produce the same key.

    Policy note: ``isoformat()`` emits ``"+00:00"`` for UTC, not ``"Z"``.
    The normalizer does NOT collapse the two. Two callers that hand in
    ``2026-04-20T00:00:00+00:00`` vs ``2026-04-20T00:00:00Z`` WILL get
    different keys. This is an intentional contract: hashing must be
    stable per-input, and canonicalizing timezone notation is the job of
    the ingestion layer (parsers normalize at the edge, hashing trusts
    what it's given). If a future story wants to collapse Z to +00:00,
    that becomes a deliberate migration with a documented hash-rotation.
    """

    def test_roundtrip_through_isoformat_yields_same_key(self):
        """A ``datetime`` and its ``isoformat()`` string must hash the
        same — that's the stability contract for the legacy path."""
        dt = datetime(2026, 4, 20, 0, 0, 0, tzinfo=timezone.utc)
        iso = dt.isoformat()
        k_dt = compute_idempotency_key(**BASE_KEY_ARGS, kdes={"t": dt})
        k_iso = compute_idempotency_key(**BASE_KEY_ARGS, kdes={"t": iso})
        assert k_dt == k_iso

    def test_offset_form_and_zulu_form_produce_different_keys(self):
        """Document the contract: the normalizer does NOT canonicalize
        ``+00:00`` vs ``Z``. If this test ever starts failing, that's a
        deliberate-break decision requiring a migration plan for
        existing idempotency_key rows."""
        k_offset = compute_idempotency_key(
            **BASE_KEY_ARGS, kdes={"t": "2026-04-20T00:00:00+00:00"}
        )
        k_zulu = compute_idempotency_key(
            **BASE_KEY_ARGS, kdes={"t": "2026-04-20T00:00:00Z"}
        )
        assert k_offset != k_zulu

    def test_str_datetime_is_no_longer_canonical(self):
        """The pre-fix behavior was ``default=str``. If this assertion
        ever flips, the normalizer has regressed."""
        dt = datetime(2026, 4, 20, tzinfo=timezone.utc)
        k_dt = compute_idempotency_key(**BASE_KEY_ARGS, kdes={"t": dt})
        k_str = compute_idempotency_key(
            **BASE_KEY_ARGS, kdes={"t": str(dt)}
        )
        # str(dt) uses a space separator ("2026-04-20 00:00:00+00:00"),
        # isoformat uses "T" ("2026-04-20T00:00:00+00:00"). They MUST
        # hash differently under the new normalizer.
        assert k_dt != k_str


# =============================================================================
# Decimal canonical form — fixed-point, no scientific notation
# =============================================================================


class TestCanonicalDecimalForm:
    def test_decimal_rounded_to_fixed_point(self):
        """``Decimal("1E+2")`` and ``Decimal("100")`` are value-equal
        and must produce the same key after normalization, because
        ``format(..., 'f')`` renders both as ``"100"`` (no scientific
        notation)."""
        k_sci = compute_idempotency_key(
            **BASE_KEY_ARGS, kdes={"q": Decimal("1E+2")}
        )
        k_plain = compute_idempotency_key(
            **BASE_KEY_ARGS, kdes={"q": Decimal("100")}
        )
        assert k_sci == k_plain

    def test_decimal_trailing_zeros_preserved(self):
        """``Decimal("10.50")`` and ``Decimal("10.5")`` are NOT
        value-equal at the representation level — the former has
        explicit trailing-zero precision. ``format(..., 'f')`` preserves
        that precision, so they hash differently. Documenting the
        contract."""
        k_50 = compute_idempotency_key(
            **BASE_KEY_ARGS, kdes={"q": Decimal("10.50")}
        )
        k_5 = compute_idempotency_key(
            **BASE_KEY_ARGS, kdes={"q": Decimal("10.5")}
        )
        assert k_50 != k_5


# =============================================================================
# Idempotency of the normalizer itself
# =============================================================================


class TestNormalizerHelper:
    def test_datetime_to_isoformat(self):
        dt = datetime(2026, 4, 20, 14, 30, tzinfo=timezone.utc)
        assert _normalize_for_hashing(dt) == "2026-04-20T14:30:00+00:00"

    def test_date_to_isoformat(self):
        assert _normalize_for_hashing(date(2026, 4, 20)) == "2026-04-20"

    def test_datetime_subclass_of_date_takes_datetime_branch(self):
        """datetime is a subclass of date — the dispatch order matters
        (datetime branch must come first)."""
        dt = datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc)
        out = _normalize_for_hashing(dt)
        # Must be the datetime form (with "T" and time), not the date
        # form (just "2026-04-20").
        assert "T" in out
        assert "12:00" in out

    def test_decimal_fixed_point(self):
        assert _normalize_for_hashing(Decimal("10.50")) == "10.50"
        assert _normalize_for_hashing(Decimal("1E+2")) == "100"

    def test_uuid_to_str(self):
        u = UUID("00000000-0000-0000-0000-00000000cafe")
        assert _normalize_for_hashing(u) == str(u)

    def test_primitives_pass_through(self):
        assert _normalize_for_hashing("hello") == "hello"
        assert _normalize_for_hashing(42) == 42
        assert _normalize_for_hashing(3.14) == 3.14
        assert _normalize_for_hashing(True) is True
        assert _normalize_for_hashing(None) is None

    def test_nested_dict(self):
        dt = datetime(2026, 4, 20, tzinfo=timezone.utc)
        nested = {"outer": {"inner": dt}}
        out = _normalize_for_hashing(nested)
        assert out == {"outer": {"inner": "2026-04-20T00:00:00+00:00"}}

    def test_nested_list(self):
        items = [Decimal("1.5"), Decimal("2.5")]
        out = _normalize_for_hashing(items)
        assert out == ["1.5", "2.5"]

    def test_tuple_becomes_list(self):
        """Tuples lose their tuple-ness through json.dumps anyway;
        the normalizer returns a list for consistency."""
        out = _normalize_for_hashing((Decimal("1"), Decimal("2")))
        assert out == ["1", "2"]
