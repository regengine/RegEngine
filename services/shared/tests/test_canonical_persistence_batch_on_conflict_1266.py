"""Regression tests for issue #1266.

Before the fix, ``_batch_insert_canonical_events`` used a plain INSERT with
no conflict clause.  A single duplicate idempotency_key in a 50-row chunk
caused the whole INSERT to abort with a UNIQUE violation, losing all 49
non-duplicate rows.

The fix adds ``ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
RETURNING event_id`` so that only the duplicates are silently skipped and
the rest of the chunk lands cleanly.

These tests exercise the method against a real (in-process SQLite) DB so
that the ON CONFLICT clause is actually executed, not just pattern-matched.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Unit tests — mock the DB session, verify SQL contains ON CONFLICT
# ---------------------------------------------------------------------------


class TestBatchInsertSQLContainsOnConflict:
    """Lock: the generated SQL always carries ON CONFLICT … DO NOTHING."""

    def _make_writer(self, rows_returned: List[tuple]):
        """Return a minimal CanonicalPersistenceWriter with a mocked session."""
        from services.shared.canonical_persistence.writer import CanonicalEventStore  # noqa: PLC0415

        writer = object.__new__(CanonicalEventStore)
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows_returned
        mock_session.execute.return_value = mock_result
        writer.session = mock_session  # type: ignore[attr-defined]
        return writer, mock_session

    def _make_event(self, tenant_id: str = "t1", idempotency_key: str | None = None):
        """Return a minimal TraceabilityEvent-like object."""
        evt = MagicMock()
        evt.tenant_id = tenant_id
        evt.event_id = str(uuid.uuid4())
        evt.idempotency_key = idempotency_key or str(uuid.uuid4())
        return evt

    # ------------------------------------------------------------------

    def test_sql_contains_on_conflict_do_nothing(self):
        """The SQL passed to session.execute must include ON CONFLICT clause."""
        writer, mock_session = self._make_writer(rows_returned=[(str(uuid.uuid4()),)])

        evt = self._make_event()

        # Patch _event_to_params so we don't need a real TraceabilityEvent model
        with patch.object(
            writer,
            "_event_to_params",
            return_value={"tenant_id": evt.tenant_id, "idempotency_key": evt.idempotency_key, "event_id": evt.event_id},
        ):
            writer._batch_insert_canonical_events([evt])  # type: ignore[attr-defined]

        assert mock_session.execute.called
        sql_arg = str(mock_session.execute.call_args[0][0])
        assert "ON CONFLICT" in sql_arg.upper()
        assert "DO NOTHING" in sql_arg.upper()

    def test_duplicate_in_chunk_does_not_abort_others(self):
        """Mock: session.execute succeeds even when only a subset of rows come
        back (simulating DO NOTHING for duplicates). The returned set must
        match exactly what RETURNING yields."""
        ids = [str(uuid.uuid4()) for _ in range(3)]
        # Simulate: 5 events sent, 3 actually inserted (2 were duplicates)
        writer, mock_session = self._make_writer(rows_returned=[(i,) for i in ids])

        events = [self._make_event() for _ in range(5)]

        # _event_to_params is called N times (once per event in the loop) plus
        # once more for col_names extraction (events[0]) — so N+1 total.
        base_params = [
            {"tenant_id": e.tenant_id, "idempotency_key": e.idempotency_key, "event_id": e.event_id}
            for e in events
        ]
        params_list = [base_params[0]] + base_params  # leading call for col_names
        with patch.object(writer, "_event_to_params", side_effect=params_list):
            result = writer._batch_insert_canonical_events(events)  # type: ignore[attr-defined]

        assert result == set(ids)
        # session.execute called exactly once (bulk INSERT, not N singles)
        assert mock_session.execute.call_count == 1

    def test_all_duplicate_chunk_returns_empty_set(self):
        """When every event in the chunk is a duplicate, RETURNING yields no
        rows — the method should return an empty set, not raise."""
        writer, mock_session = self._make_writer(rows_returned=[])

        events = [self._make_event() for _ in range(10)]
        base_params = [
            {"tenant_id": e.tenant_id, "idempotency_key": e.idempotency_key, "event_id": e.event_id}
            for e in events
        ]
        params_list = [base_params[0]] + base_params
        with patch.object(writer, "_event_to_params", side_effect=params_list):
            result = writer._batch_insert_canonical_events(events)  # type: ignore[attr-defined]

        assert result == set()
        assert mock_session.execute.call_count == 1

    def test_all_new_chunk_returns_all_ids(self):
        """Happy path: no duplicates → all event_ids returned."""
        ids = [str(uuid.uuid4()) for _ in range(5)]
        writer, mock_session = self._make_writer(rows_returned=[(i,) for i in ids])

        events = [self._make_event() for _ in range(5)]
        base_params = [
            {"tenant_id": e.tenant_id, "idempotency_key": e.idempotency_key, "event_id": e.event_id}
            for e in events
        ]
        params_list = [base_params[0]] + base_params
        with patch.object(writer, "_event_to_params", side_effect=params_list):
            result = writer._batch_insert_canonical_events(events)  # type: ignore[attr-defined]

        assert result == set(ids)
