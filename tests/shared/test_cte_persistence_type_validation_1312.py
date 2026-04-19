"""Regression tests for #1312 — strict CTE event-type allowlist.

Before this fix, ``CTEPersistence.store_event`` and
``store_events_batch`` accepted any string as ``event_type``: a caller
could write ``"HARVESTING "`` (trailing space), ``"harvest"``,
``"XFORM"``, ``"[object Object]"``, or the empty string, and the value
was hashed, chained, and persisted as a valid CTE. Downstream code
(FDA export, graph sync, rules engine) then had to guess which
spellings represented which FSMA events — masking real
miscategorization bugs.

The fix adds a Python gate at each persistence entry point that
rejects anything not exactly matching one of the seven FSMA 204
§1.1310 CTE types. The gate mirrors the ``CTEType`` enum in
``shared.canonical_event``; we avoid importing the enum directly to
keep the persistence-layer validation independent of Pydantic.

Pattern: mocked SQLAlchemy ``Session`` so tests can run without
Postgres. We focus on behavior visible to the caller (ValueError
raised / not raised) and never hit the DB.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple
from unittest.mock import MagicMock

import pytest

from shared.cte_persistence.core import (
    CTEPersistence,
    FSMA_204_CTE_TYPES,
    _validate_cte_event_type,
)


# ---------------------------------------------------------------------------
# Minimal fake session (same shape as test_cte_persistence_hardening.py)
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def scalar(self):
        return self._scalar


class _FakeSession:
    def __init__(self):
        self.calls: List[Tuple[str, Dict[str, Any]]] = []
        self._rules: List[Tuple[re.Pattern, Any]] = []

    def add_rule(self, pattern: str, result):
        self._rules.append((re.compile(pattern, re.IGNORECASE | re.DOTALL), result))

    def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        self.calls.append((sql, dict(params or {})))
        for pat, result in self._rules:
            if pat.search(sql):
                if callable(result):
                    return result(sql, params or {})
                return result
        return _FakeResult()

    def begin_nested(self):
        ns = MagicMock()
        ns.rollback = MagicMock()
        return ns


def _persistence() -> CTEPersistence:
    sess = _FakeSession()
    sess.add_rule(r"SELECT idempotency_key", _FakeResult(rows=[]))
    sess.add_rule(r"FROM fsma\.cte_events\s+WHERE idempotency_key", _FakeResult(rows=[]))
    sess.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))
    return CTEPersistence(session=sess)


def _valid_single_kwargs(**overrides):
    base = {
        "tenant_id": "t-1",
        "event_type": "harvesting",
        "traceability_lot_code": "TLC-1",
        "product_description": "Lettuce",
        "quantity": 10.0,
        "unit_of_measure": "kg",
        "event_timestamp": "2026-04-15T12:00:00+00:00",
        "source": "api",
    }
    base.update(overrides)
    return base


def _valid_batch_event(**overrides):
    evt = {
        "event_type": "harvesting",
        "traceability_lot_code": "TLC-1",
        "product_description": "Lettuce",
        "quantity": 10.0,
        "unit_of_measure": "kg",
        "event_timestamp": "2026-04-15T12:00:00+00:00",
        "kdes": {"farm_name": "Acme"},
    }
    evt.update(overrides)
    return evt


# ---------------------------------------------------------------------------
# Allowlist contents — FSMA 204 §1.1310
# ---------------------------------------------------------------------------


class TestFSMA204AllowlistContents_Issue1312:
    def test_allowlist_has_exactly_seven_types(self):
        """FSMA 204 §1.1310 enumerates exactly seven CTE categories.
        A drift here (additions or deletions) should require a
        deliberate, test-gated change."""
        assert len(FSMA_204_CTE_TYPES) == 7

    def test_allowlist_contains_all_seven_fsma_types(self):
        expected = {
            "harvesting",
            "cooling",
            "initial_packing",
            "first_land_based_receiving",
            "shipping",
            "receiving",
            "transformation",
        }
        assert FSMA_204_CTE_TYPES == expected

    def test_allowlist_matches_canonical_event_enum(self):
        """The persistence allowlist must match the canonical ``CTEType``
        enum one-for-one. If the enum grows, this test forces a
        matching update to the persistence allowlist."""
        from shared.canonical_event import CTEType

        enum_values = {e.value for e in CTEType}
        assert FSMA_204_CTE_TYPES == enum_values, (
            "shared.cte_persistence.FSMA_204_CTE_TYPES diverged from "
            "shared.canonical_event.CTEType — both must stay in sync"
        )


# ---------------------------------------------------------------------------
# _validate_cte_event_type unit coverage
# ---------------------------------------------------------------------------


class TestValidateFunction_Issue1312:
    @pytest.mark.parametrize("valid", sorted(FSMA_204_CTE_TYPES))
    def test_all_seven_canonical_types_accepted(self, valid):
        assert _validate_cte_event_type(valid) == valid

    @pytest.mark.parametrize(
        "malformed",
        [
            "HARVESTING",          # wrong case
            "Harvesting",          # title case
            "harvesting ",         # trailing space
            " harvesting",         # leading space
            "harvesting\n",        # trailing newline
            "harvest",             # truncated
            "XFORM",               # shortened / nickname
            "picking",             # not in FSMA 204 (not a CTE)
            "[object Object]",     # JS-serialized garbage
            "",                    # empty string
            "null",                # stringified null
            "undefined",           # stringified undefined
        ],
    )
    def test_malformed_strings_rejected(self, malformed):
        with pytest.raises(ValueError) as exc:
            _validate_cte_event_type(malformed)
        # The error message must quote the offending value so caller
        # logs can diagnose what went wrong.
        assert repr(malformed) in str(exc.value) or malformed in str(exc.value)

    @pytest.mark.parametrize(
        "not_a_string",
        [None, 0, 1.0, True, False, [], {}, object(), b"harvesting"],
    )
    def test_non_string_inputs_rejected(self, not_a_string):
        with pytest.raises(ValueError):
            _validate_cte_event_type(not_a_string)

    def test_field_name_appears_in_error(self):
        """The ``field=`` keyword lets batch callers identify which row
        was bad. Default is 'event_type'."""
        with pytest.raises(ValueError, match="event_type"):
            _validate_cte_event_type("bogus")
        with pytest.raises(ValueError, match="events\\[7\\].event_type"):
            _validate_cte_event_type("bogus", field="events[7].event_type")


# ---------------------------------------------------------------------------
# store_event integration
# ---------------------------------------------------------------------------


class TestStoreEventValidation_Issue1312:
    def test_valid_event_type_accepted(self):
        p = _persistence()
        result = p.store_event(**_valid_single_kwargs(event_type="shipping"))
        assert result.success is True

    def test_trailing_whitespace_rejected(self):
        """Pre-fix: 'HARVESTING ' (with trailing space) would hash as a
        distinct event and persist as a valid row."""
        p = _persistence()
        with pytest.raises(ValueError, match="FSMA 204"):
            p.store_event(**_valid_single_kwargs(event_type="harvesting "))

    def test_wrong_case_rejected(self):
        p = _persistence()
        with pytest.raises(ValueError, match="FSMA 204"):
            p.store_event(**_valid_single_kwargs(event_type="HARVESTING"))

    def test_unknown_type_rejected(self):
        p = _persistence()
        with pytest.raises(ValueError, match="FSMA 204"):
            p.store_event(**_valid_single_kwargs(event_type="custom_type"))

    def test_empty_string_rejected(self):
        p = _persistence()
        with pytest.raises(ValueError):
            p.store_event(**_valid_single_kwargs(event_type=""))

    def test_none_rejected(self):
        p = _persistence()
        with pytest.raises(ValueError):
            p.store_event(**_valid_single_kwargs(event_type=None))

    def test_validation_runs_before_insert(self):
        """A bad event_type must NOT reach the database. This guards
        against a regression where validation was moved past the
        INSERT and the DB-level CHECK became the only defense."""
        sess = _FakeSession()
        # No rules registered — every execute returns empty _FakeResult.
        p = CTEPersistence(session=sess)
        with pytest.raises(ValueError):
            p.store_event(**_valid_single_kwargs(event_type="garbage"))

        cte_inserts = [c for c in sess.calls if "INSERT INTO fsma.cte_events" in c[0]]
        assert cte_inserts == [], (
            "validation must fire before any INSERT — found cte_events INSERT "
            "despite invalid event_type"
        )

    def test_all_seven_types_persist(self):
        """Sanity: every FSMA 204 type is accepted by store_event."""
        for cte_type in sorted(FSMA_204_CTE_TYPES):
            p = _persistence()
            result = p.store_event(**_valid_single_kwargs(event_type=cte_type))
            assert result.success is True, f"type={cte_type} should persist"


# ---------------------------------------------------------------------------
# store_events_batch integration
# ---------------------------------------------------------------------------


class TestStoreEventsBatchValidation_Issue1312:
    def test_valid_batch_accepted(self):
        p = _persistence()
        results = p.store_events_batch(
            tenant_id="t-1",
            events=[_valid_batch_event(event_type=t) for t in sorted(FSMA_204_CTE_TYPES)],
        )
        assert len(results) == 7
        assert all(r.success for r in results)

    def test_one_bad_event_fails_the_whole_batch(self):
        """Batch validation is strict: a single malformed event_type
        rejects the entire batch. Partial-persistence would produce a
        hash chain where ``sequence_num`` gaps map to silently-dropped
        rows, breaking verify_chain."""
        p = _persistence()
        evts = [
            _valid_batch_event(),                        # ok
            _valid_batch_event(event_type="HARVEST"),    # bad (wrong case + truncated)
            _valid_batch_event(event_type="shipping"),   # ok
        ]
        with pytest.raises(ValueError, match="FSMA 204"):
            p.store_events_batch(tenant_id="t-1", events=evts)

    def test_batch_validation_runs_before_any_insert(self):
        sess = _FakeSession()
        p = CTEPersistence(session=sess)
        evts = [
            _valid_batch_event(),
            _valid_batch_event(event_type="garbage"),
        ]
        with pytest.raises(ValueError):
            p.store_events_batch(tenant_id="t-1", events=evts)

        cte_inserts = [c for c in sess.calls if "INSERT INTO fsma.cte_events" in c[0]]
        assert cte_inserts == [], (
            "no cte_events INSERT should fire when any batch entry has "
            "a bad event_type"
        )

    def test_missing_event_type_rejected(self):
        p = _persistence()
        evt = _valid_batch_event()
        evt.pop("event_type")
        with pytest.raises(ValueError):
            p.store_events_batch(tenant_id="t-1", events=[evt])

    def test_caller_input_is_not_mutated(self):
        """Batch validator normalizes via ``evt = dict(evt)`` so the
        caller's original dict must not be mutated even when we
        overwrite ``event_type`` in the copy."""
        p = _persistence()
        evt = _valid_batch_event()
        original = dict(evt)
        p.store_events_batch(tenant_id="t-1", events=[evt])
        assert evt == original, "caller input was mutated during validation"
