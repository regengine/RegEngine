"""Regression tests for the legacy dual-write mapping cluster.

Covers four already-applied fixes in
``shared.canonical_persistence.legacy_dual_write`` and
``shared.canonical_persistence.writer``:

* #2514 — canonical ``EventStatus`` → legacy ``validation_status`` map.
  ``superseded`` / ``draft`` previously passed through raw and violated
  the ``cte_events.validation_status`` CHECK domain
  (``'valid','rejected','warning'``), rolling back the canonical row too.
* #2532 — KDE values are serialized as JSON text and cast with
  ``CAST(:kde_value AS jsonb)`` (not bound as ``str(value)`` against an
  implicit text→jsonb cast that fails for ordinary values).
* #2533 — the canonical chain INSERT is guarded with
  ``WHERE EXISTS (... traceability_events ...)`` so a no-op canonical
  INSERT with no re-selected winner cannot write an orphan chain row.
* #2535 — the full facility reference is carried into
  ``location_gln`` / ``location_name`` instead of being dropped unless
  it is exactly 13 chars.

These use the ``FakeSession`` infra from
``test_canonical_persistence_hardening`` — no live DB.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from shared.canonical_event import EventStatus
from shared.canonical_persistence import legacy_dual_write as migration
from shared.canonical_persistence.writer import CanonicalEventStore

from tests.shared.test_canonical_persistence_hardening import (
    FakeSession,
    _FakeResult,
    _make_event,
)


def _capture_cte_insert(session: FakeSession) -> dict:
    """Return the params dict of the cte_events INSERT call."""
    for sql, params in session.calls:
        if "INSERT INTO fsma.cte_events" in sql:
            return params
    raise AssertionError("no cte_events INSERT was issued")


def _capture_kde_inserts(session: FakeSession) -> list[dict]:
    return [params for sql, params in session.calls if "INSERT INTO fsma.cte_kdes" in sql]


# ---------------------------------------------------------------------------
# #2514 — EventStatus → validation_status mapping
# ---------------------------------------------------------------------------


class TestValidationStatusMapping_Issue2514:
    @pytest.mark.parametrize(
        "status,expected",
        [
            (EventStatus.ACTIVE, "valid"),
            (EventStatus.SUPERSEDED, "valid"),
            (EventStatus.REJECTED, "rejected"),
            (EventStatus.DRAFT, "valid"),
        ],
    )
    def test_all_statuses_map_into_check_domain(self, status, expected) -> None:
        session = FakeSession()
        event = _make_event()
        event.status = status
        migration.dual_write_legacy(session, event)
        params = _capture_cte_insert(session)
        assert params["validation_status"] == expected
        assert params["validation_status"] in {"valid", "rejected", "warning"}

    def test_superseded_no_longer_passes_raw_value(self) -> None:
        """The old code wrote the raw enum value ``superseded`` which the
        CHECK constraint rejects. Assert it now maps to a legal value."""
        session = FakeSession()
        event = _make_event()
        event.status = EventStatus.SUPERSEDED
        migration.dual_write_legacy(session, event)
        params = _capture_cte_insert(session)
        assert params["validation_status"] != "superseded"

    def test_unknown_status_falls_back_to_valid(self) -> None:
        assert migration._map_validation_status("some_future_status") == "valid"


# ---------------------------------------------------------------------------
# #2532 — KDE JSON serialization + explicit ::jsonb cast
# ---------------------------------------------------------------------------


class TestKdeJsonbSerialization_Issue2532:
    def test_dict_and_string_kdes_are_json_text(self) -> None:
        session = FakeSession()
        event = _make_event()
        event.kdes = {
            "consignee": {"gln": "0614141000005"},
            "lot_code": "LOT-XYZ",
            "input_lot_codes": ["A", "B"],
        }
        migration.dual_write_legacy(session, event)

        kde_calls = {p["kde_key"]: p["kde_value"] for p in _capture_kde_inserts(session)}
        # Every bound value must be valid JSON text that round-trips.
        assert json.loads(kde_calls["consignee"]) == {"gln": "0614141000005"}
        assert json.loads(kde_calls["lot_code"]) == "LOT-XYZ"
        assert json.loads(kde_calls["input_lot_codes"]) == ["A", "B"]
        # A bare string must NOT be bound as the raw token (would fail the
        # implicit text->jsonb cast).
        assert kde_calls["lot_code"] != "LOT-XYZ"

    def test_insert_uses_explicit_jsonb_cast(self) -> None:
        session = FakeSession()
        event = _make_event()
        event.kdes = {"lot_code": "LOT-1"}
        migration.dual_write_legacy(session, event)
        kde_sql = next(sql for sql, _ in session.calls if "INSERT INTO fsma.cte_kdes" in sql)
        assert "CAST(:kde_value AS jsonb)" in kde_sql


# ---------------------------------------------------------------------------
# #2533 — orphan-chain guard on the canonical chain INSERT
# ---------------------------------------------------------------------------


class TestOrphanChainGuard_Issue2533:
    def test_chain_insert_has_where_exists_guard(self) -> None:
        """The canonical ``_insert_chain_entry`` must guard with
        ``WHERE EXISTS (... traceability_events ...)`` so a chain row is
        only written when the referenced event actually exists."""
        session = FakeSession()
        store = CanonicalEventStore(session=session, dual_write=False, skip_chain_write=False)
        store._insert_chain_entry(
            tenant_id=str(uuid4()),
            event_id=str(uuid4()),
            sequence_num=1,
            event_hash="sha",
            previous_chain_hash=None,
            chain_hash="ch",
        )
        chain_sql = next(sql for sql, _ in session.calls if "INSERT INTO fsma.hash_chain" in sql)
        assert "WHERE EXISTS" in chain_sql
        assert "FROM fsma.traceability_events" in chain_sql
        # Must be the SELECT ... WHERE EXISTS shape, not a bare VALUES.
        assert "SELECT :tenant_id" in chain_sql

    def test_no_orphan_chain_when_event_absent(self) -> None:
        """When the guarded INSERT finds no matching event, no chain row
        lands. Simulate by having the fake session report zero affected
        rows for the chain INSERT; the call must not raise."""
        session = FakeSession()

        def _chain_noop(sql, params):
            # The WHERE EXISTS yielded no row — DB writes nothing.
            return _FakeResult(rows=[])

        session.add_rule(r"INSERT INTO fsma\.hash_chain", _chain_noop)
        store = CanonicalEventStore(session=session, dual_write=False, skip_chain_write=False)
        # Should not raise even though the guard suppressed the insert.
        store._insert_chain_entry(
            tenant_id=str(uuid4()),
            event_id=str(uuid4()),
            sequence_num=1,
            event_hash="sha",
            previous_chain_hash=None,
            chain_hash="ch",
        )


# ---------------------------------------------------------------------------
# #2535 — facility reference is carried, not dropped on len()!=13
# ---------------------------------------------------------------------------


class TestFacilityReferenceCarried_Issue2535:
    def test_sgln_urn_is_not_dropped(self) -> None:
        session = FakeSession()
        event = _make_event()
        event.from_facility_reference = "urn:epc:id:sgln:0614141.00001.0"
        event.to_facility_reference = None
        migration.dual_write_legacy(session, event)
        params = _capture_cte_insert(session)
        assert params["location_gln"] == "urn:epc:id:sgln:0614141.00001.0"
        assert params["location_name"] == "urn:epc:id:sgln:0614141.00001.0"

    def test_to_facility_only_event_records_location(self) -> None:
        session = FakeSession()
        event = _make_event()
        event.from_facility_reference = None
        event.to_facility_reference = "urn:gs1:414:0614141000012"
        migration.dual_write_legacy(session, event)
        params = _capture_cte_insert(session)
        assert params["location_gln"] == "urn:gs1:414:0614141000012"
        assert params["location_name"] == "urn:gs1:414:0614141000012"
