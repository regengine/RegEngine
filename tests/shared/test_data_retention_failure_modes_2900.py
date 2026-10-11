"""#2900 — the retention layer must fail loudly, not silently no-op.

``RetentionPolicy`` values were interpolated straight into SQL as table names.
Against ``alembic upgrade head`` none of them resolve, and the migrated schema
contains no ``deleted_at`` column at all — so every soft-delete raised
``UndefinedTable``. ``soft_delete_record`` caught the exception with a bare
``except Exception``, logged, and returned ``False`` **without rolling back**,
which left the caller's transaction in ``InFailedSqlTransaction``.

The regression these tests lock in is not "the SQL works" (it cannot, until a
soft-delete column is designed and migrated) but "the failure is loud and does
not poison the caller":

  * a schema fault propagates as ``RetentionSchemaError`` instead of a quiet
    ``False`` the caller reads as "row not found";
  * the session is rolled back on every failure path;
  * the cleanup job rolls back between policies so one broken policy does not
    take down the rest of the sweep with it;
  * the resource→relation map is complete and honest about what is missing.

The live counterpart is ``tests/shared/test_retention_relations_live.py``.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from shared.audit_logging import AuditActor, AuditStorageError
from shared.data_retention import (
    _RESOURCE_RELATIONS,
    RETENTION_CONFIGS,
    DataRetentionManager,
    DeletionRequest,
    RetentionPolicy,
    RetentionSchemaError,
    cleanup_deleted_records_job,
)
from sqlalchemy.exc import ProgrammingError


def _undefined_table(name: str) -> ProgrammingError:
    """The error a real Postgres raises for these statements."""
    return ProgrammingError(
        f"UPDATE {name} SET deleted_at = ...",
        {},
        Exception(f'relation "{name}" does not exist'),
    )


def _manager():
    mgr = DataRetentionManager(audit_logger=MagicMock())
    mgr.audit_logger.log_data_modification = AsyncMock(return_value=None)
    mgr.audit_logger.log = AsyncMock(return_value=None)
    return mgr


def _actor():
    return AuditActor(actor_type="user", actor_id=str(uuid.uuid4()))


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# soft_delete_record
# ---------------------------------------------------------------------------


def test_soft_delete_propagates_a_missing_relation_instead_of_returning_false():
    """A phantom target must not read as "no matching row"."""
    mgr = _manager()
    db = MagicMock()
    db.execute.side_effect = _undefined_table("user_account")

    with pytest.raises(RetentionSchemaError) as exc:
        _run(
            mgr.soft_delete_record(
                db=db,
                resource_type="user_account",
                record_id=str(uuid.uuid4()),
                policy=RetentionPolicy.USER_ACCOUNT,
                deletion_request=DeletionRequest.USER_INITIATED,
                actor=_actor(),
                tenant_id=None,
            )
        )

    assert "user_account" in str(exc.value)


def test_soft_delete_rolls_back_the_caller_session_on_failure():
    """Without the rollback the caller's next statement dies in
    ``InFailedSqlTransaction`` — which is how #2900's 500s were produced."""
    mgr = _manager()
    db = MagicMock()
    db.execute.side_effect = _undefined_table("supplier_contact")

    with pytest.raises(RetentionSchemaError):
        _run(
            mgr.soft_delete_record(
                db=db,
                resource_type="supplier_contact",
                record_id=str(uuid.uuid4()),
                policy=RetentionPolicy.SUPPLIER_CONTACT,
                deletion_request=DeletionRequest.USER_INITIATED,
                actor=_actor(),
                tenant_id=uuid.uuid4(),
            )
        )

    db.rollback.assert_called_once()


def test_soft_delete_still_returns_false_for_a_genuinely_absent_row():
    """Rowcount 0 is a legitimate "nothing to do", not a schema fault — it must
    stay a quiet ``False`` so the loud path keeps its meaning."""
    mgr = _manager()
    db = MagicMock()
    result = MagicMock()
    result.rowcount = 0
    db.execute.return_value = result

    ok = _run(
        mgr.soft_delete_record(
            db=db,
            resource_type="user_account",
            record_id=str(uuid.uuid4()),
            policy=RetentionPolicy.USER_ACCOUNT,
            deletion_request=DeletionRequest.USER_INITIATED,
            actor=_actor(),
            tenant_id=None,
        )
    )

    assert ok is False


def test_process_deletion_request_reports_the_schema_fault_to_its_caller():
    """``process_deletion_request`` is the erasure endpoint's entry point. It
    must surface the failure in the result dict rather than returning a bare
    ``soft_deleted=False`` indistinguishable from "row already gone"."""
    mgr = _manager()
    db = MagicMock()
    db.execute.side_effect = _undefined_table("user_account")

    result = _run(
        mgr.process_deletion_request(
            db=db,
            resource_type="user_account",
            record_id=str(uuid.uuid4()),
            policy=RetentionPolicy.USER_ACCOUNT,
            deletion_request=DeletionRequest.USER_INITIATED,
            actor=_actor(),
        )
    )

    assert result["soft_deleted"] is False
    assert result["hard_delete_scheduled"] is False
    assert result["error"], "the caller must be told WHY nothing was deleted"
    assert "user_account" in result["error"]


# ---------------------------------------------------------------------------
# cleanup_deleted_records_job
# ---------------------------------------------------------------------------


def test_cleanup_job_rolls_back_between_policies(monkeypatch):
    """One broken policy poisons the transaction; without a rollback every
    later policy AND the audit anonymisation step fail as collateral."""
    import shared.data_retention as dr

    monkeypatch.setenv("AUDIT_INTEGRITY_KEY", "test-audit-integrity-key")

    db = MagicMock()
    db.execute.side_effect = _undefined_table("user_account")

    class _Ctx:
        def __enter__(self):
            return db

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(dr, "get_db", lambda: _Ctx())

    stats = _run(cleanup_deleted_records_job())

    # One rollback per policy that failed (AUDIT_LOG is handled separately).
    failing_policies = [p for p in RETENTION_CONFIGS if p is not RetentionPolicy.AUDIT_LOG]
    assert db.rollback.call_count >= len(failing_policies), (
        f"expected a rollback after each failed policy sweep, got {db.rollback.call_count}"
    )
    assert stats["errors"] >= len(failing_policies)
    assert stats["hard_deleted_total"] == 0


# ---------------------------------------------------------------------------
# the resource -> relation map
# ---------------------------------------------------------------------------


def test_every_retention_policy_declares_a_backing_relation():
    """The root cause was that no such mapping existed: the enum value simply
    *was* the table name, so a policy could never be wrong on paper."""
    for policy in RetentionPolicy:
        assert policy.value in _RESOURCE_RELATIONS, (
            f"RetentionPolicy.{policy.name} has no entry in _RESOURCE_RELATIONS — "
            "add one (or None, documented) before this policy is swept"
        )


def test_declared_relations_are_schema_qualified():
    """``None`` means "no such relation exists"; anything else must name a
    real, schema-qualified relation so ``to_regclass`` can check it."""
    for resource, relation in _RESOURCE_RELATIONS.items():
        if relation is None:
            continue
        assert "." in relation, f"{resource} -> {relation!r} must be schema-qualified (e.g. 'public.users')"


# ---------------------------------------------------------------------------
# audit failure after a committed delete (#3234 follow-up)
# ---------------------------------------------------------------------------


def _ok_update(db):
    """One matching row: the UPDATE/DELETE commits, then the audit write runs."""
    result = MagicMock()
    result.rowcount = 1
    db.execute.return_value = result
    return db


def _audit_failing_manager():
    mgr = _manager()
    mgr.audit_logger.log_data_modification = AsyncMock(
        side_effect=AuditStorageError("audit event evt-1 was not persisted")
    )
    return mgr


def test_soft_delete_reraises_audit_failure_after_commit():
    """The UPDATE already committed, so the row IS deleted. A quiet False
    would read as row not found and skip the hard-delete schedule."""
    mgr = _audit_failing_manager()
    db = _ok_update(MagicMock())

    with pytest.raises(AuditStorageError):
        _run(
            mgr.soft_delete_record(
                db=db,
                resource_type="user_account",
                record_id=str(uuid.uuid4()),
                policy=RetentionPolicy.USER_ACCOUNT,
                deletion_request=DeletionRequest.USER_INITIATED,
                actor=_actor(),
                tenant_id=None,
            )
        )

    db.rollback.assert_called_once()


def test_hard_delete_reraises_audit_failure_after_commit():
    """The DELETE already committed, so the row IS gone. A quiet False
    would make the cleanup job report a delete error for a delete that
    happened, with no audit row to show for it."""
    mgr = _audit_failing_manager()
    db = _ok_update(MagicMock())

    with pytest.raises(AuditStorageError):
        _run(
            mgr.hard_delete_record(
                db=db,
                resource_type="user_account",
                record_id=str(uuid.uuid4()),
                actor=_actor(),
            )
        )

    db.rollback.assert_called_once()


def test_process_deletion_request_reports_committed_delete_with_failed_audit():
    """Committed delete plus failed audit must read as deleted-with-error,
    not as soft_deleted False with a null error."""
    mgr = _audit_failing_manager()
    db = _ok_update(MagicMock())

    result = _run(
        mgr.process_deletion_request(
            db=db,
            resource_type="user_account",
            record_id=str(uuid.uuid4()),
            policy=RetentionPolicy.USER_ACCOUNT,
            deletion_request=DeletionRequest.USER_INITIATED,
            actor=_actor(),
        )
    )

    assert result["soft_deleted"] is True
    assert result["hard_delete_scheduled"] is False
    assert "audit" in result["error"]


def test_process_deletion_request_reports_failed_schedule_audit():
    """Delete and its audit both succeed, but the follow-up schedule audit
    fails: the delete must still read as done, with the error attached."""
    mgr = _manager()
    mgr.audit_logger.log = AsyncMock(
        side_effect=AuditStorageError("audit event evt-2 was not persisted")
    )
    db = _ok_update(MagicMock())

    result = _run(
        mgr.process_deletion_request(
            db=db,
            resource_type="user_account",
            record_id=str(uuid.uuid4()),
            policy=RetentionPolicy.USER_ACCOUNT,
            deletion_request=DeletionRequest.USER_INITIATED,
            actor=_actor(),
        )
    )

    assert result["soft_deleted"] is True
    assert result["hard_delete_scheduled"] is False
    assert "audit" in result["error"]
