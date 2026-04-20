"""Tests for #1334 (append-only enforcement) and #1335 (LEGACY DeprecationWarning).

#1334 — store_event and store_events_batch must raise DuplicateEventError when
         an event with the same sha256_hash already exists in fsma.cte_events.
         The migration v073 trigger SQL must be present in the migration file.

#1335 — store_event and store_events_batch must emit DeprecationWarning so
         callers know to migrate to CanonicalEventStore.
         Confirm that webhook_router_v2 and epcis/persistence already dual-write
         to the canonical path (verifying no pure-LEGACY-only callers remain
         for WRITE operations).
"""

from __future__ import annotations

import importlib
import inspect
import re
import warnings
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from services.shared.cte_persistence.core import (
    CTEPersistence,
    _assert_not_exists,
)
from services.shared.cte_persistence.models import DuplicateEventError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session(existing_sha: Optional[str] = None, existing_id: Optional[str] = None):
    """Return a MagicMock SQLAlchemy session pre-configured for tests.

    If ``existing_sha`` is set the session will return a row from
    ``_assert_not_exists``'s SELECT so that a DuplicateEventError is raised.
    """
    session = MagicMock()

    # Default: no existing row for _assert_not_exists
    def _execute_side_effect(stmt, params=None, **kw):
        result = MagicMock()
        # Detect the append-only check by looking for sha256_hash in the SQL
        sql_text = str(stmt)
        if "sha256_hash" in sql_text and existing_sha and params and params.get("sha") == existing_sha:
            row = MagicMock()
            row.__getitem__ = lambda self, i: existing_id or "existing-uuid"
            result.fetchone.return_value = row
        else:
            result.fetchone.return_value = None
            result.fetchall.return_value = []
        return result

    session.execute.side_effect = _execute_side_effect
    session.begin_nested.return_value = MagicMock()
    return session


# ===========================================================================
# #1334 — _assert_not_exists unit tests
# ===========================================================================

class TestAssertNotExists_Issue1334:
    """Unit tests for the _assert_not_exists helper."""

    def test_no_existing_row_does_not_raise(self):
        """When the SELECT returns None, no exception is raised."""
        session = MagicMock()
        result = MagicMock()
        result.fetchone.return_value = None
        session.execute.return_value = result

        _assert_not_exists("deadbeef" * 8, "tenant-1", session)  # must not raise

    def test_existing_row_raises_duplicate_event_error(self):
        """When the SELECT returns a row, DuplicateEventError is raised."""
        sha = "aabbccdd" * 8
        existing_id = str(uuid4())

        session = MagicMock()
        result = MagicMock()
        row = MagicMock()
        row.__getitem__ = lambda self, i: existing_id
        result.fetchone.return_value = row
        session.execute.return_value = result

        with pytest.raises(DuplicateEventError) as exc_info:
            _assert_not_exists(sha, "tenant-1", session)

        err = exc_info.value
        assert err.sha256_hash == sha
        assert err.event_id == existing_id

    def test_uses_parameterised_sql_only(self):
        """Verify the SELECT uses :sha and :tid bind params (no interpolation)."""
        session = MagicMock()
        result = MagicMock()
        result.fetchone.return_value = None
        session.execute.return_value = result

        sha = "cafebabe" * 8
        tid = "tenant-xyz"
        _assert_not_exists(sha, tid, session)

        call_args = session.execute.call_args
        # second positional/keyword arg is the params dict
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("params") or call_args[0][1]
        assert params["sha"] == sha
        assert params["tid"] == tid


# ===========================================================================
# #1334 — store_event raises DuplicateEventError on overwrite attempt
# ===========================================================================

class TestStoreEventAppendOnly_Issue1334:
    """store_event must raise DuplicateEventError when sha256_hash already exists."""

    _VALID_EVENT_KWARGS: Dict[str, Any] = dict(
        tenant_id="tenant-1",
        event_type="receiving",
        traceability_lot_code="LOT-001",
        product_description="Romaine lettuce",
        quantity=50.0,
        unit_of_measure="kg",
        event_timestamp="2026-01-15T10:00:00+00:00",
        source="api",
    )

    def test_raises_on_duplicate_sha256(self):
        """A second store_event for the same content raises DuplicateEventError."""
        from services.shared.cte_persistence.hashing import compute_event_hash

        # Compute the hash that will be produced by store_event
        event_id_placeholder = "any"  # store_event generates its own uuid4
        sha = compute_event_hash(
            event_id_placeholder,
            "receiving",
            "LOT-001",
            "Romaine lettuce",
            50.0,
            "kg",
            None,
            None,
            "2026-01-15T10:00:00+00:00",
            {},
        )
        # We can't predict the uuid4 exactly, so we patch _assert_not_exists
        # to simulate it finding an existing row.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            session = MagicMock()
            # First call (idempotency check) — no existing row
            first_result = MagicMock()
            first_result.fetchone.return_value = None
            first_result.fetchall.return_value = []
            session.execute.return_value = first_result

            persistence = CTEPersistence(session)

            with patch(
                "services.shared.cte_persistence.core._assert_not_exists",
                side_effect=DuplicateEventError("existing-id", sha),
            ):
                with pytest.raises(DuplicateEventError) as exc_info:
                    persistence.store_event(**self._VALID_EVENT_KWARGS)

        assert exc_info.value.sha256_hash == sha

    def test_assert_not_exists_called_before_insert(self):
        """_assert_not_exists is called with the computed sha256 and tenant_id."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            session = MagicMock()
            result = MagicMock()
            result.fetchone.return_value = None
            result.fetchall.return_value = []
            session.execute.return_value = result
            session.begin_nested.return_value = MagicMock()

            persistence = CTEPersistence(session)
            calls_made: List[tuple] = []

            real_assert = _assert_not_exists

            def spy_assert(sha, tid, sess):
                calls_made.append((sha, tid))
                # Don't raise — let store_event proceed normally

            with patch(
                "services.shared.cte_persistence.core._assert_not_exists",
                side_effect=spy_assert,
            ):
                persistence.store_event(**self._VALID_EVENT_KWARGS)

        assert len(calls_made) == 1
        sha_called, tid_called = calls_made[0]
        assert tid_called == "tenant-1"
        assert len(sha_called) == 64  # sha256 hex string


# ===========================================================================
# #1334 — store_events_batch raises DuplicateEventError on overwrite attempt
# ===========================================================================

class TestStoreEventsBatchAppendOnly_Issue1334:
    """store_events_batch must raise DuplicateEventError when sha256 already exists."""

    def test_raises_on_duplicate_sha256_in_batch(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            session = MagicMock()
            result = MagicMock()
            result.fetchone.return_value = None
            result.fetchall.return_value = []
            session.execute.return_value = result
            session.begin_nested.return_value = MagicMock()

            persistence = CTEPersistence(session)
            event = {
                "event_type": "shipping",
                "traceability_lot_code": "LOT-BATCH-001",
                "product_description": "Spinach",
                "quantity": 10.0,
                "unit_of_measure": "cases",
                "event_timestamp": "2026-01-16T08:00:00+00:00",
            }

            with patch(
                "services.shared.cte_persistence.core._assert_not_exists",
                side_effect=DuplicateEventError("dup-id", "sha" * 16),
            ):
                with pytest.raises(DuplicateEventError):
                    persistence.store_events_batch("tenant-1", [event])


# ===========================================================================
# #1335 — DeprecationWarning on LEGACY write methods
# ===========================================================================

class TestLegacyDeprecationWarning_Issue1335:
    """store_event and store_events_batch must emit DeprecationWarning."""

    _VALID_EVENT_KWARGS: Dict[str, Any] = dict(
        tenant_id="tenant-1",
        event_type="receiving",
        traceability_lot_code="LOT-WARN-001",
        product_description="Cucumber",
        quantity=5.0,
        unit_of_measure="kg",
        event_timestamp="2026-02-01T12:00:00+00:00",
        source="api",
    )

    def _make_noop_session(self):
        session = MagicMock()
        result = MagicMock()
        result.fetchone.return_value = None
        result.fetchall.return_value = []
        session.execute.return_value = result
        session.begin_nested.return_value = MagicMock()
        return session

    def test_store_event_emits_deprecation_warning(self):
        session = self._make_noop_session()
        persistence = CTEPersistence(session)

        with patch("services.shared.cte_persistence.core._assert_not_exists"):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                persistence.store_event(**self._VALID_EVENT_KWARGS)

        dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(dep_warnings) >= 1
        messages = " ".join(str(x.message) for x in dep_warnings)
        assert "LEGACY" in messages
        assert "1335" in messages
        assert "CanonicalEventStore" in messages

    def test_store_events_batch_emits_deprecation_warning(self):
        session = self._make_noop_session()
        persistence = CTEPersistence(session)
        event = {
            "event_type": "shipping",
            "traceability_lot_code": "LOT-WARN-002",
            "product_description": "Tomatoes",
            "quantity": 20.0,
            "unit_of_measure": "kg",
            "event_timestamp": "2026-02-01T13:00:00+00:00",
        }
        with patch("services.shared.cte_persistence.core._assert_not_exists"):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                persistence.store_events_batch("tenant-1", [event])

        dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(dep_warnings) >= 1
        messages = " ".join(str(x.message) for x in dep_warnings)
        assert "LEGACY" in messages
        assert "1335" in messages
        assert "CanonicalEventStore" in messages


# ===========================================================================
# #1335 — Callers already dual-write to canonical path (import check)
# ===========================================================================

class TestCallersDualWriteToCanonical_Issue1335:
    """Verify that the primary write callers also call CanonicalEventStore.

    webhook_router_v2 and epcis/persistence are the two callers that write
    via CTEPersistence.store_event / store_events_batch.  Both should also
    import and call CanonicalEventStore so that even while the LEGACY path
    is still in use, canonical data is being written in parallel.
    """

    def _get_source(self, module_path: str) -> str:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_mod", module_path)
        source = spec.loader.get_source("_mod")  # type: ignore[attr-defined]
        return source or ""

    def test_webhook_router_v2_imports_canonical_event_store(self):
        import os
        path = os.path.join(
            os.path.dirname(__file__),
            "../../../../services/ingestion/app/webhook_router_v2.py",
        )
        path = os.path.normpath(path)
        with open(path) as f:
            source = f.read()
        assert "CanonicalEventStore" in source, (
            "webhook_router_v2.py must reference CanonicalEventStore "
            "(dual-write to canonical path, #1335)"
        )

    def test_epcis_persistence_imports_canonical_event_store(self):
        import os
        path = os.path.join(
            os.path.dirname(__file__),
            "../../../../services/ingestion/app/epcis/persistence.py",
        )
        path = os.path.normpath(path)
        with open(path) as f:
            source = f.read()
        assert "CanonicalEventStore" in source, (
            "epcis/persistence.py must reference CanonicalEventStore "
            "(dual-write to canonical path, #1335)"
        )


# ===========================================================================
# #1334 — Migration file contains trigger SQL
# ===========================================================================

class TestMigrationTriggerSQL_Issue1334:
    """The v073 migration file must contain the expected trigger DDL."""

    def _get_migration_source(self) -> str:
        import os
        path = os.path.join(
            os.path.dirname(__file__),
            "../../../../alembic/versions/"
            "20260420_v073_cte_events_append_only_trigger_1334.py",
        )
        path = os.path.normpath(path)
        with open(path) as f:
            return f.read()

    def test_migration_contains_before_update_or_delete_trigger(self):
        source = self._get_migration_source()
        assert "BEFORE UPDATE OR DELETE" in source, (
            "Migration v073 must create a BEFORE UPDATE OR DELETE trigger "
            "on fsma.cte_events"
        )

    def test_migration_contains_trigger_name(self):
        source = self._get_migration_source()
        assert "cte_events_no_update_delete" in source

    def test_migration_contains_raise_exception(self):
        source = self._get_migration_source()
        assert "RAISE EXCEPTION" in source

    def test_migration_references_issue_1334(self):
        source = self._get_migration_source()
        assert "1334" in source

    def test_migration_has_upgrade_and_downgrade(self):
        source = self._get_migration_source()
        assert "def upgrade" in source
        assert "def downgrade" in source
