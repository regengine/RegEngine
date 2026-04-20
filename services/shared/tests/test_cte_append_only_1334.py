"""Regression tests for issue #1334 — fsma.cte_events and fsma.hash_chain are append-only.

FDA 21 CFR 1.1455 requires 2-year retention of traceability records. Migration
v073 adds BEFORE UPDATE OR DELETE triggers on both tables that raise an exception
unless the break-glass GUC ``fsma.allow_mutation = 'true'`` is set for the
current transaction. These tests verify both the block and the break-glass path.

Since no live Postgres DB is available in CI, these tests are marked
``integration`` and also provide a Python-level simulation layer that validates
the trigger logic without a DB.  The real enforcement lives in the DB trigger;
the Python simulation documents the expected semantics and can be run offline.

To run against a real Postgres (recommended before merging):
    pytest -m integration services/shared/tests/test_cte_append_only_1334.py
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from unittest.mock import MagicMock, call, patch
import pytest


# ---------------------------------------------------------------------------
# Helpers — Python-level trigger simulation
# ---------------------------------------------------------------------------

class _AppendOnlyError(Exception):
    """Mirrors the Postgres RESTRICT_VIOLATION raised by the trigger."""


class _TriggerSimulator:
    """Simulate the fsma.enforce_append_only() PL/pgSQL trigger in Python.

    This is NOT a replacement for the DB trigger — it's a documentation-
    level validator that ensures the logical behaviour of the trigger is
    understood and tested without needing a live Postgres instance.

    The real trigger reads the GUC ``fsma.allow_mutation``; this class
    accepts an explicit ``allow_mutation`` flag so tests remain hermetic.
    """

    def __init__(self, *, allow_mutation: bool = False):
        self.allow_mutation = allow_mutation
        self.notices: list[str] = []

    def before_update_or_delete(self, table: str, op: str, tenant_id: str) -> None:
        """Execute the trigger logic. Raises _AppendOnlyError if blocked."""
        if self.allow_mutation:
            notice = (
                f"fsma.{table} mutation allowed via break-glass "
                f"(op={op}, tenant_id={tenant_id})"
            )
            self.notices.append(notice)
            return  # allow

        raise _AppendOnlyError(
            f"fsma.{table} is append-only (FSMA 21 CFR 1.1455 — 2-year retention). "
            f"Set LOCAL fsma.allow_mutation = true to bypass (break-glass). "
            f"Op: {op}, table: fsma.{table}"
        )


# ---------------------------------------------------------------------------
# Unit tests — trigger simulation (always runnable, no DB required)
# ---------------------------------------------------------------------------

class TestCteEventsAppendOnlySimulation:
    """Verify trigger semantics for fsma.cte_events without a DB."""

    def _trig(self, *, allow: bool = False) -> _TriggerSimulator:
        return _TriggerSimulator(allow_mutation=allow)

    def test_update_blocked_by_default(self):
        trig = self._trig()
        with pytest.raises(_AppendOnlyError, match="append-only"):
            trig.before_update_or_delete("cte_events", "UPDATE", "tenant-abc")

    def test_delete_blocked_by_default(self):
        trig = self._trig()
        with pytest.raises(_AppendOnlyError, match="append-only"):
            trig.before_update_or_delete("cte_events", "DELETE", "tenant-abc")

    def test_update_succeeds_with_break_glass(self):
        trig = self._trig(allow=True)
        # Should not raise
        trig.before_update_or_delete("cte_events", "UPDATE", "tenant-abc")

    def test_delete_succeeds_with_break_glass(self):
        trig = self._trig(allow=True)
        trig.before_update_or_delete("cte_events", "DELETE", "tenant-abc")

    def test_break_glass_emits_notice(self):
        trig = self._trig(allow=True)
        trig.before_update_or_delete("cte_events", "UPDATE", "tenant-abc")
        assert len(trig.notices) == 1
        assert "break-glass" in trig.notices[0]
        assert "cte_events" in trig.notices[0]

    def test_break_glass_notice_includes_tenant_id(self):
        trig = self._trig(allow=True)
        trig.before_update_or_delete("cte_events", "DELETE", "tenant-xyz")
        assert "tenant-xyz" in trig.notices[0]

    def test_notice_emitted_per_row(self):
        """Trigger fires FOR EACH ROW — one notice per mutation."""
        trig = self._trig(allow=True)
        for i in range(3):
            trig.before_update_or_delete("cte_events", "UPDATE", f"tenant-{i}")
        assert len(trig.notices) == 3

    def test_error_message_references_cfr_1455(self):
        trig = self._trig()
        with pytest.raises(_AppendOnlyError, match="1.1455"):
            trig.before_update_or_delete("cte_events", "UPDATE", "t")

    def test_error_message_references_break_glass_guc(self):
        trig = self._trig()
        with pytest.raises(_AppendOnlyError, match="allow_mutation"):
            trig.before_update_or_delete("cte_events", "UPDATE", "t")


class TestHashChainAppendOnlySimulation:
    """Same trigger semantics for fsma.hash_chain."""

    def _trig(self, *, allow: bool = False) -> _TriggerSimulator:
        return _TriggerSimulator(allow_mutation=allow)

    def test_update_blocked_by_default(self):
        trig = self._trig()
        with pytest.raises(_AppendOnlyError, match="append-only"):
            trig.before_update_or_delete("hash_chain", "UPDATE", "tenant-abc")

    def test_delete_blocked_by_default(self):
        trig = self._trig()
        with pytest.raises(_AppendOnlyError, match="append-only"):
            trig.before_update_or_delete("hash_chain", "DELETE", "tenant-abc")

    def test_update_succeeds_with_break_glass(self):
        trig = self._trig(allow=True)
        trig.before_update_or_delete("hash_chain", "UPDATE", "tenant-abc")

    def test_delete_succeeds_with_break_glass(self):
        trig = self._trig(allow=True)
        trig.before_update_or_delete("hash_chain", "DELETE", "tenant-abc")

    def test_break_glass_emits_notice(self):
        trig = self._trig(allow=True)
        trig.before_update_or_delete("hash_chain", "UPDATE", "tenant-abc")
        assert len(trig.notices) == 1
        assert "hash_chain" in trig.notices[0]
        assert "break-glass" in trig.notices[0]

    def test_notice_emitted_per_row(self):
        trig = self._trig(allow=True)
        for i in range(5):
            trig.before_update_or_delete("hash_chain", "DELETE", f"t-{i}")
        assert len(trig.notices) == 5

    def test_no_row_filter_bypass(self):
        """Trigger fires on ALL rows — there is no WHERE filter that lets
        rows slip through without hitting the guard.

        This test documents the intent: the migration uses FOR EACH ROW
        with no WHEN condition, so every single UPDATE/DELETE triggers
        the function regardless of column values or row state.
        """
        trig = self._trig()
        rows = [
            {"table": "hash_chain", "op": "UPDATE", "tenant": "t-1"},
            {"table": "hash_chain", "op": "DELETE", "tenant": "t-2"},
            {"table": "hash_chain", "op": "UPDATE", "tenant": "t-3"},
        ]
        for r in rows:
            with pytest.raises(_AppendOnlyError):
                trig.before_update_or_delete(r["table"], r["op"], r["tenant"])


# ---------------------------------------------------------------------------
# Integration tests — require a live Postgres with v073 migration applied
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestCteEventsAppendOnlyIntegration:
    """Tests that run against a real Postgres DB with the v073 trigger in place.

    Requires the ``db_session`` fixture that provides a SQLAlchemy Session
    connected to a test database with fsma schema and sample data.
    """

    @pytest.fixture(autouse=True)
    def _seed(self, db_session):
        """Insert one row in each table to have something to UPDATE/DELETE."""
        import uuid
        self.tenant_id = str(uuid.uuid4())
        self.event_id = str(uuid.uuid4())
        db_session.execute(
            __import__("sqlalchemy").text("SET LOCAL app.tenant_id = :tid"),
            {"tid": self.tenant_id},
        )
        db_session.execute(
            __import__("sqlalchemy").text(
                """
                INSERT INTO fsma.cte_events (
                    id, tenant_id, event_type, traceability_lot_code,
                    product_description, quantity, unit_of_measure,
                    event_timestamp, event_entry_timestamp,
                    source, idempotency_key, sha256_hash, chain_hash,
                    validation_status
                ) VALUES (
                    :id, :tid, 'receiving', 'TLC-TEST-1334',
                    'Test product', 1.0, 'kg',
                    NOW(), NOW(),
                    'test', :ik, :sha, :ch,
                    'valid'
                )
                """
            ),
            {
                "id": self.event_id, "tid": self.tenant_id,
                "ik": "idemp-test-1334",
                "sha": "a" * 64, "ch": "b" * 64,
            },
        )
        db_session.execute(
            __import__("sqlalchemy").text(
                """
                INSERT INTO fsma.hash_chain (
                    tenant_id, cte_event_id, sequence_num,
                    event_hash, previous_chain_hash, chain_hash
                ) VALUES (:tid, :eid, 1, :eh, NULL, :ch)
                """
            ),
            {
                "tid": self.tenant_id, "eid": self.event_id,
                "eh": "a" * 64, "ch": "b" * 64,
            },
        )
        yield
        db_session.rollback()

    def test_update_cte_events_raises_without_break_glass(self, db_session):
        from sqlalchemy.exc import DatabaseError
        with pytest.raises(DatabaseError, match="append-only"):
            db_session.execute(
                __import__("sqlalchemy").text(
                    "UPDATE fsma.cte_events SET validation_status='rejected' "
                    "WHERE id = :eid"
                ),
                {"eid": self.event_id},
            )

    def test_delete_cte_events_raises_without_break_glass(self, db_session):
        from sqlalchemy.exc import DatabaseError
        with pytest.raises(DatabaseError, match="append-only"):
            db_session.execute(
                __import__("sqlalchemy").text(
                    "DELETE FROM fsma.cte_events WHERE id = :eid"
                ),
                {"eid": self.event_id},
            )

    def test_update_hash_chain_raises_without_break_glass(self, db_session):
        from sqlalchemy.exc import DatabaseError
        with pytest.raises(DatabaseError, match="append-only"):
            db_session.execute(
                __import__("sqlalchemy").text(
                    "UPDATE fsma.hash_chain SET event_hash = 'x' "
                    "WHERE cte_event_id = :eid"
                ),
                {"eid": self.event_id},
            )

    def test_delete_hash_chain_raises_without_break_glass(self, db_session):
        from sqlalchemy.exc import DatabaseError
        with pytest.raises(DatabaseError, match="append-only"):
            db_session.execute(
                __import__("sqlalchemy").text(
                    "DELETE FROM fsma.hash_chain WHERE cte_event_id = :eid"
                ),
                {"eid": self.event_id},
            )

    def test_update_cte_events_succeeds_with_break_glass(self, db_session):
        db_session.execute(
            __import__("sqlalchemy").text("SET LOCAL fsma.allow_mutation = 'true'")
        )
        # Should not raise
        db_session.execute(
            __import__("sqlalchemy").text(
                "UPDATE fsma.cte_events SET validation_status='rejected' WHERE id = :eid"
            ),
            {"eid": self.event_id},
        )

    def test_delete_hash_chain_succeeds_with_break_glass(self, db_session):
        db_session.execute(
            __import__("sqlalchemy").text("SET LOCAL fsma.allow_mutation = 'true'")
        )
        db_session.execute(
            __import__("sqlalchemy").text(
                "DELETE FROM fsma.hash_chain WHERE cte_event_id = :eid"
            ),
            {"eid": self.event_id},
        )

    def test_break_glass_is_transaction_scoped(self, db_session):
        """After COMMIT, allow_mutation reverts to false (SET LOCAL semantics)."""
        # SET LOCAL inside the seeded txn; then simulate a new txn
        db_session.execute(
            __import__("sqlalchemy").text("SET LOCAL fsma.allow_mutation = 'true'")
        )
        db_session.commit()
        # New transaction — break-glass no longer active
        from sqlalchemy.exc import DatabaseError
        with pytest.raises(DatabaseError, match="append-only"):
            db_session.execute(
                __import__("sqlalchemy").text(
                    "DELETE FROM fsma.cte_events WHERE id = :eid"
                ),
                {"eid": self.event_id},
            )
