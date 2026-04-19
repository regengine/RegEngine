"""
Regression tests for #1312 — ``CTEPersistence.store_event`` accepted
``event_type`` as a free-form string. A caller could write
``"HARVESTING "`` (trailing space), ``"harvest"``, ``"XFORM"``, or
``"[object Object]"`` and the event would be hashed and chain-computed
before Postgres's CHECK constraint finally rejected the row — surfacing
as a confusing IntegrityError long after the chain lock was taken.

The fix adds an application-level guard (``_validate_event_type``) at
the top of ``store_event`` and inside the batch loop. The guard:
  * Rejects ``None``, non-strings, and empty/whitespace-only values.
  * Requires strict equality — trailing whitespace, wrong case, and
    unknown tokens all fail fast.
  * Raises ``ValueError`` with the list of allowed types.

The tests drive the writer with a mocked session so cap semantics and
error paths are exercised without touching Postgres.
"""
from __future__ import annotations

import pytest

from shared.cte_persistence.core import (
    CTEPersistence,
    _ALLOWED_CTE_TYPES,
    _validate_event_type,
)

from tests.shared.test_cte_persistence_hardening import (
    FakeSession,
    _FakeResult,
    _base_event,
)


# ---------------------------------------------------------------------------
# Pure-function guard — _validate_event_type
# ---------------------------------------------------------------------------


class TestValidateEventType_Issue1312:
    """Unit-level coverage of the guard. No DB, no store."""

    @pytest.mark.parametrize("valid", sorted(_ALLOWED_CTE_TYPES))
    def test_accepts_all_seven_fsma_types(self, valid):
        assert _validate_event_type(valid) == valid

    def test_rejects_none(self):
        with pytest.raises(ValueError, match="required"):
            _validate_event_type(None)

    def test_rejects_non_string(self):
        with pytest.raises(ValueError, match="required"):
            _validate_event_type(42)

    def test_rejects_empty_string(self):
        with pytest.raises(ValueError, match="required"):
            _validate_event_type("")

    def test_rejects_trailing_whitespace(self):
        """The whole point of the guard: ``'harvesting '`` must not
        normalize silently. The caller has a bug and should be told."""
        with pytest.raises(ValueError, match="not a recognized"):
            _validate_event_type("harvesting ")

    def test_rejects_leading_whitespace(self):
        with pytest.raises(ValueError, match="not a recognized"):
            _validate_event_type(" harvesting")

    def test_rejects_wrong_case_uppercase(self):
        with pytest.raises(ValueError, match="not a recognized"):
            _validate_event_type("HARVESTING")

    def test_rejects_wrong_case_titlecase(self):
        with pytest.raises(ValueError, match="not a recognized"):
            _validate_event_type("Shipping")

    def test_rejects_truncated_token(self):
        """``"harvest"`` is a common typo — not a valid CTE type."""
        with pytest.raises(ValueError, match="not a recognized"):
            _validate_event_type("harvest")

    def test_rejects_abbreviation(self):
        with pytest.raises(ValueError, match="not a recognized"):
            _validate_event_type("XFORM")

    def test_rejects_javascript_coercion(self):
        """``"[object Object]"`` appears when a JS caller accidentally
        passes an object where a string was expected."""
        with pytest.raises(ValueError, match="not a recognized"):
            _validate_event_type("[object Object]")

    def test_rejects_growing_even_though_canonical_accepts_it(self):
        """canonical_persistence accepts ``'growing'`` (schema v057);
        the legacy ``fsma.cte_events`` CHECK does NOT accept it. The
        guard here must track what THIS module's schema allows, not
        the parallel canonical schema. If 'growing' is accepted here,
        every row with event_type='growing' will fail at INSERT with
        an opaque IntegrityError."""
        assert "growing" not in _ALLOWED_CTE_TYPES
        with pytest.raises(ValueError, match="not a recognized"):
            _validate_event_type("growing")

    def test_error_message_lists_allowed_types(self):
        """The error must be actionable — name the valid values so
        the caller can see what to use."""
        with pytest.raises(ValueError) as exc_info:
            _validate_event_type("bogus")
        msg = str(exc_info.value)
        for allowed in _ALLOWED_CTE_TYPES:
            assert allowed in msg


# ---------------------------------------------------------------------------
# Integration via store_event — fail-fast before hash/chain lock
# ---------------------------------------------------------------------------


class TestStoreEventRejectsInvalidType_Issue1312:
    """The guard must fire BEFORE the chain lock and BEFORE any SQL is
    issued. Regression proof: we run the store with a session that
    would fail loudly on ANY execute call — if the SQL rail is hit,
    the guard was skipped."""

    def _exploding_session(self):
        session = FakeSession()

        def _explode(sql, params):
            raise AssertionError(
                f"SQL issued despite invalid event_type: {sql[:80]!r}"
            )

        session.add_rule(r".", _explode)
        return session

    def test_store_event_rejects_trailing_whitespace_before_sql(self):
        session = self._exploding_session()
        persistence = CTEPersistence(session)
        with pytest.raises(ValueError, match="not a recognized"):
            persistence.store_event(
                tenant_id="tenant-1",
                event_type="harvesting ",  # trailing space
                traceability_lot_code="TLC-1",
                product_description="Lettuce",
                quantity=10.0,
                unit_of_measure="kg",
                event_timestamp="2026-04-15T12:00:00Z",
            )
        # No SQL was issued at all.
        assert session.calls == []

    def test_store_event_rejects_uppercase(self):
        session = self._exploding_session()
        persistence = CTEPersistence(session)
        with pytest.raises(ValueError, match="not a recognized"):
            persistence.store_event(
                tenant_id="tenant-1",
                event_type="HARVESTING",
                traceability_lot_code="TLC-1",
                product_description="Lettuce",
                quantity=10.0,
                unit_of_measure="kg",
                event_timestamp="2026-04-15T12:00:00Z",
            )
        assert session.calls == []

    def test_store_event_rejects_none(self):
        session = self._exploding_session()
        persistence = CTEPersistence(session)
        with pytest.raises(ValueError, match="required"):
            persistence.store_event(
                tenant_id="tenant-1",
                event_type=None,  # type: ignore[arg-type]
                traceability_lot_code="TLC-1",
                product_description="Lettuce",
                quantity=10.0,
                unit_of_measure="kg",
                event_timestamp="2026-04-15T12:00:00Z",
            )
        assert session.calls == []


# ---------------------------------------------------------------------------
# Integration via store_events_batch — per-row validation
# ---------------------------------------------------------------------------


class TestStoreEventsBatchValidatesPerRow_Issue1312:
    """A bad row in a batch must fail the batch. We don't want one
    bogus ``event_type`` to poison the chain for the other rows — and
    we don't want to partially-commit either."""

    def test_batch_rejects_if_any_event_type_invalid(self):
        session = FakeSession()
        # Advisory lock is the only pre-guard call; allow that to pass.
        session.add_rule(r"pg_advisory_xact_lock", _FakeResult())
        persistence = CTEPersistence(session)

        events = [
            _base_event(event_type="harvesting"),
            _base_event(event_type="Shipping"),  # wrong case
            _base_event(event_type="receiving"),
        ]

        with pytest.raises(ValueError, match="not a recognized"):
            persistence.store_events_batch(
                tenant_id="tenant-1", events=events
            )

    def test_batch_with_all_valid_types_passes_guard(self):
        """Sanity-check the positive path — every valid type makes it
        past the guard (the batch may still do other SQL work that
        needs mocking, but that's not this test's concern)."""
        for cte_type in _ALLOWED_CTE_TYPES:
            evt = _base_event(event_type=cte_type)
            assert _validate_event_type(evt["event_type"]) == cte_type


# ---------------------------------------------------------------------------
# Allowed-set contract — schema sync invariant
# ---------------------------------------------------------------------------


class TestAllowedSetContract_Issue1312:
    """The guard's allowed set MUST stay in sync with the DB CHECK
    constraint in ``alembic/sql/V037__obligation_cte_rules.sql``.
    This test pins the size and membership so a schema drift is a
    loud test failure, not a silent IntegrityError in production."""

    def test_allowed_set_has_exactly_seven_fsma_types(self):
        assert len(_ALLOWED_CTE_TYPES) == 7

    def test_allowed_set_matches_fsma_204_1310(self):
        expected = {
            "harvesting",
            "cooling",
            "initial_packing",
            "first_land_based_receiving",
            "shipping",
            "receiving",
            "transformation",
        }
        assert _ALLOWED_CTE_TYPES == expected

    def test_allowed_set_is_frozen(self):
        """Guard against accidental mutation at runtime — the set must
        be immutable so one test's teardown can't leak into another."""
        assert isinstance(_ALLOWED_CTE_TYPES, frozenset)
