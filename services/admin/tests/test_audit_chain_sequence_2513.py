"""Regression coverage for #2513 — per-tenant audit chain sequencing.

The admin tamper-evident audit chain (``AuditLogger.log_event``) read the
chain head and inserted without any per-tenant lock and without a
contiguous ``sequence_num``, so concurrent same-tenant writers could fork
the chain off a shared ``prev_hash`` and a removed middle row left no gap
signal.

These tests pin the fix:
* ``log_event`` acquires ``pg_advisory_xact_lock(hashtext(tenant_id))``
  before reading the chain head (SQL-capture, SQLite path no-ops).
* Sequential ``log_event`` calls assign contiguous per-tenant
  ``sequence_num`` and chain off the previous entry (SQLite-backed).
* The ``UNIQUE (tenant_id, sequence_num)`` constraint exists and a
  duplicate sequence is rejected.
* ``verify_chain`` flags a removed middle row via a ``sequence_gap`` and
  still passes a healthy contiguous chain.

Tracks GitHub issue #2513.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

import pytest

service_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("sqlalchemy")

from services.admin.app.audit import AuditLogger, compute_integrity_hash  # noqa: E402
from services.admin.app.audit_integrity import verify_chain  # noqa: E402
from services.admin.app.sqlalchemy_models import AuditLogModel  # noqa: E402

TENANT = UUID("00000000-0000-0000-0000-000000000099")
TENANT_OTHER = UUID("00000000-0000-0000-0000-0000000000aa")
ACTOR = UUID("00000000-0000-0000-0000-000000000001")


# ---------------------------------------------------------------------------
# Advisory lock ordering (mock session — no live DB)
# ---------------------------------------------------------------------------


def _mk_mock_session(prev_hash=None, prev_seq=None):
    """Mock session whose .one_or_none() returns the chain head row."""
    session = MagicMock()
    # No real bind -> _acquire_chain_lock skips the SQLite shortcut and
    # issues the advisory-lock execute() against this mock.
    session.bind = None
    head_row = None if prev_hash is None and prev_seq is None else (prev_hash, prev_seq)
    session.execute.return_value.one_or_none.return_value = head_row
    added: list = []
    session.add.side_effect = lambda e: added.append(e)
    session.flush.side_effect = lambda: setattr(added[0], "id", 1) if added else None
    session._added = added
    return session


class TestAdvisoryLock:
    def test_log_event_acquires_advisory_lock_before_head_read(self):
        """``pg_advisory_xact_lock`` must fire before the chain-head SELECT
        so concurrent same-tenant writers serialize (#2513)."""
        session = _mk_mock_session(prev_hash=None)

        AuditLogger.log_event(
            db=session,
            tenant_id=TENANT,
            event_type="auth.login",
            action="login",
            event_category="security",
            actor_id=ACTOR,
        )

        # Collect the textual SQL of each execute() call, in order.
        sql_calls = [str(c.args[0]) for c in session.execute.call_args_list if c.args]
        lock_idx = next((i for i, s in enumerate(sql_calls) if "pg_advisory_xact_lock" in s), None)
        assert lock_idx is not None, "log_event must acquire an advisory lock (#2513)"
        # The lock call must be the first SQL the function issues, before
        # the chain-head read.
        assert lock_idx == 0, "advisory lock must precede the chain-head read"

    def test_advisory_lock_is_keyed_by_tenant(self):
        session = _mk_mock_session(prev_hash=None)

        AuditLogger.log_event(
            db=session,
            tenant_id=TENANT,
            event_type="auth.login",
            action="login",
            event_category="security",
        )

        lock_call = next(
            (c for c in session.execute.call_args_list if c.args and "pg_advisory_xact_lock" in str(c.args[0])),
            None,
        )
        assert lock_call is not None
        params = lock_call.args[1]
        assert params["tid"] == str(TENANT)


# ---------------------------------------------------------------------------
# Sequence assignment + UNIQUE constraint (SQLite-backed)
# ---------------------------------------------------------------------------


class TestSequenceAssignment:
    def test_sequential_writes_get_contiguous_sequence_and_chain(self, db_session):
        ids = []
        for _ in range(3):
            entry_id = AuditLogger.log_event(
                db=db_session,
                tenant_id=TENANT,
                event_type="auth.login",
                action="login",
                event_category="security",
                actor_id=ACTOR,
            )
            db_session.flush()
            ids.append(entry_id)

        rows = (
            db_session.query(AuditLogModel)
            .filter(AuditLogModel.tenant_id == TENANT)
            .order_by(AuditLogModel.sequence_num.asc())
            .all()
        )
        assert [r.sequence_num for r in rows] == [1, 2, 3]
        # Each entry chains off the previous one's integrity hash.
        assert rows[0].prev_hash is None
        assert rows[1].prev_hash == rows[0].integrity_hash
        assert rows[2].prev_hash == rows[1].integrity_hash

    def test_sequences_are_independent_per_tenant(self, db_session):
        AuditLogger.log_event(db=db_session, tenant_id=TENANT, event_type="e", action="a", event_category="security")
        AuditLogger.log_event(
            db=db_session, tenant_id=TENANT_OTHER, event_type="e", action="a", event_category="security"
        )
        AuditLogger.log_event(db=db_session, tenant_id=TENANT, event_type="e", action="a", event_category="security")
        db_session.flush()

        seqs_t = [
            r.sequence_num
            for r in db_session.query(AuditLogModel)
            .filter(AuditLogModel.tenant_id == TENANT)
            .order_by(AuditLogModel.sequence_num.asc())
            .all()
        ]
        seqs_other = [
            r.sequence_num
            for r in db_session.query(AuditLogModel).filter(AuditLogModel.tenant_id == TENANT_OTHER).all()
        ]
        assert seqs_t == [1, 2]
        assert seqs_other == [1]

    def test_unique_constraint_present(self):
        """UNIQUE (tenant_id, sequence_num) must be declared on the model
        so a forked chain surfaces as an IntegrityError (#2513)."""
        uniques = [c for c in AuditLogModel.__table__.constraints if c.__class__.__name__ == "UniqueConstraint"]
        cols = {tuple(c.name for c in u.columns) for u in uniques}
        assert ("tenant_id", "sequence_num") in cols

    def test_duplicate_sequence_rejected(self, db_session):
        """Inserting a second row with the same (tenant_id, sequence_num)
        violates the UNIQUE constraint."""
        from sqlalchemy.exc import IntegrityError

        AuditLogger.log_event(db=db_session, tenant_id=TENANT, event_type="e", action="a", event_category="security")
        db_session.flush()

        dup = AuditLogModel(
            tenant_id=TENANT,
            event_type="e",
            event_category="security",
            action="a",
            severity="info",
            sequence_num=1,
            integrity_hash="x" * 64,
        )
        db_session.add(dup)
        with pytest.raises(IntegrityError):
            db_session.flush()


# ---------------------------------------------------------------------------
# verify_chain — sequence contiguity / gap detection
# ---------------------------------------------------------------------------


def _entry(seq, prev_hash, tenant="t1", ts=None):
    ts = ts or f"2026-01-01T00:00:0{seq}Z"
    h = compute_integrity_hash(
        prev_hash=prev_hash,
        tenant_id=tenant,
        timestamp=ts,
        event_type="data.write",
        action="create",
        resource_id=None,
        metadata={},
        sequence_num=seq,
    )
    return {
        "id": seq,
        "tenant_id": tenant,
        "timestamp": ts,
        "event": {"type": "data.write", "action": "create"},
        "resource": {"id": None},
        "metadata": {},
        "integrity": {"prev_hash": prev_hash, "hash": h, "sequence_num": seq},
    }


class TestVerifyChainSequence:
    def test_contiguous_chain_valid(self):
        e1 = _entry(1, None)
        e2 = _entry(2, e1["integrity"]["hash"])
        e3 = _entry(3, e2["integrity"]["hash"])
        result = verify_chain([e1, e2, e3])
        assert result["valid"] is True, result
        assert result["verified"] == 3

    def test_removed_middle_row_flagged_as_gap(self):
        """A deleted middle row (seq 2 missing) is flagged as a sequence
        gap — a distinct, contiguity-specific error."""
        e1 = _entry(1, None)
        e2 = _entry(2, e1["integrity"]["hash"])
        e3 = _entry(3, e2["integrity"]["hash"])
        # Simulate seq 2 deleted: export omits it. e3 still references e2's
        # hash so prev_hash linkage is intact, but the sequence jumps 1->3.
        result = verify_chain([e1, e3])
        assert result["valid"] is False
        assert any(err["error"] == "sequence_gap" for err in result["errors"]), result
        gap = next(err for err in result["errors"] if err["error"] == "sequence_gap")
        assert gap["expected"] == 2
        assert gap["actual"] == 3
