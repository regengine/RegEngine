"""Regression tests for #1092 — /v1/account/erasure was broken end-to-end.

The GDPR right-to-erasure endpoint failed in production for two reasons
that #1441 did not fully close:

1. ``AuditActor(actor_email=...)`` raised ``TypeError`` — the field on
   ``AuditActor`` is ``email``, not ``actor_email``.  Every erasure
   request died before reaching the retention layer.

2. ``anonymize_audit_logs`` ran batch retention-threshold anonymization
   across ALL users whose audit rows exceeded 24 months -- it never
   targeted a specific ``user_id``.  This is the wrong semantic for a
   user-initiated GDPR Article 17 request.  And even when called
   correctly, the method attempts ``UPDATE audit_logs SET ...`` which
   the append-only trigger (V30__audit_logs_tamper_evident.sql) blocks.

These tests exercise the per-user anonymization helper introduced to
close #1092 and ensure the AuditActor construction path works.
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.audit_logging import AuditActor
from shared.data_retention import (
    DataRetentionManager,
    DeletionRequest,
    RetentionPolicy,
)


TENANT = uuid.uuid4()
USER = uuid.uuid4()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _manager():
    mgr = DataRetentionManager(audit_logger=MagicMock())
    # Short-circuit audit writes so the mocked DB doesn't need a real
    # audit_logs table.  The unit tests assert on the *call shape* not
    # the persisted row.
    mgr.audit_logger.log_data_modification = AsyncMock(return_value=None)
    mgr.audit_logger.log = AsyncMock(return_value=None)
    return mgr


def _db_with_count(count: int = 0):
    db = MagicMock()
    # The per-user method runs COUNT(*) FROM audit_logs then an
    # audit_logger.log call.  Stub the fetchone to return a (count,)
    # row so records_affected is deterministic.
    count_result = MagicMock()
    count_result.fetchone.return_value = (count,)
    db.execute.return_value = count_result
    return db


def _actor():
    return AuditActor(actor_type="user", actor_id=str(USER))


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# #1092 — AuditActor constructor signature
# ---------------------------------------------------------------------------


@pytest.mark.security
def test_audit_actor_uses_email_not_actor_email():
    """Regression: AuditActor's field is ``email``, not ``actor_email``.

    The erasure endpoint was calling ``AuditActor(actor_email=...)``
    which raised TypeError on every request and blocked all GDPR
    right-to-erasure requests from completing.  Locking in the correct
    field name so a future rename that reintroduces ``actor_email`` on
    the constructor fails CI loudly.
    """
    # This must NOT raise
    actor = AuditActor(
        actor_type="user", actor_id=str(USER), email="user@example.com"
    )
    assert actor.email == "user@example.com"

    # And the old, wrong name must raise
    with pytest.raises(TypeError, match="actor_email"):
        AuditActor(
            actor_type="user", actor_id=str(USER), actor_email="user@example.com"
        )


# ---------------------------------------------------------------------------
# #1092 — new anonymize_audit_logs_for_user method
# ---------------------------------------------------------------------------


@pytest.mark.security
def test_anonymize_for_user_requires_user_id():
    mgr = _manager()
    db = _db_with_count()
    with pytest.raises(ValueError, match="user_id is required"):
        _run(
            mgr.anonymize_audit_logs_for_user(
                db=db,
                user_id=None,  # type: ignore[arg-type]
                tenant_id=TENANT,
                actor=_actor(),
            )
        )


@pytest.mark.security
def test_anonymize_for_user_requires_tenant_id():
    mgr = _manager()
    db = _db_with_count()
    with pytest.raises(ValueError, match="tenant_id is required"):
        _run(
            mgr.anonymize_audit_logs_for_user(
                db=db,
                user_id=USER,
                tenant_id=None,  # type: ignore[arg-type]
                actor=_actor(),
            )
        )


@pytest.mark.security
def test_anonymize_for_user_counts_blast_radius():
    """The method must count audit rows authored by the user so callers
    can surface the blast radius in the erasure response."""
    mgr = _manager()
    db = _db_with_count(count=17)

    records_affected, errors = _run(
        mgr.anonymize_audit_logs_for_user(
            db=db, user_id=USER, tenant_id=TENANT, actor=_actor(),
        )
    )

    assert records_affected == 17
    assert errors == 0

    # The blast-radius SELECT must be tenant-scoped AND actor-scoped --
    # never query cross-tenant audit logs.
    assert db.execute.called
    sql_arg, params = db.execute.call_args.args
    sql = str(sql_arg)
    assert "SELECT COUNT(*) FROM audit_logs" in sql
    assert "tenant_id = :tenant_id" in sql
    assert "actor_id = :actor_id" in sql
    assert params["tenant_id"] == str(TENANT)
    assert params["actor_id"] == str(USER)


@pytest.mark.security
def test_anonymize_for_user_writes_append_only_marker():
    """The core GDPR compliance guarantee: we emit an append-only
    audit-log row describing the anonymization, NOT an UPDATE against
    historical audit_logs (which the V30 trigger rejects)."""
    mgr = _manager()
    db = _db_with_count(count=3)

    _run(
        mgr.anonymize_audit_logs_for_user(
            db=db, user_id=USER, tenant_id=TENANT, actor=_actor(),
        )
    )

    # The audit_logger.log call is the append-only marker.
    assert mgr.audit_logger.log.called
    kwargs = mgr.audit_logger.log.call_args.kwargs
    assert kwargs["action"] == "gdpr_anonymize_user"
    details = kwargs["details"]
    assert details["gdpr_article"] == 17
    assert details["redacted_user_id"] == str(USER)
    assert details["redacted_tenant_id"] == str(TENANT)
    assert details["records_affected"] == 3
    assert "email" in details["redacted_fields"]
    # Tags must include gdpr tag so compliance exports can find the
    # anonymization orders.
    tags = kwargs["tags"]
    assert "gdpr" in tags
    assert "per_user" in tags


@pytest.mark.security
def test_anonymize_for_user_never_issues_update_on_audit_logs():
    """Negative-case: the method must NEVER attempt
    ``UPDATE audit_logs`` — the immutability trigger rejects it and
    would cascade into a failed transaction.  The only DB call is the
    read-only COUNT."""
    mgr = _manager()

    # Capture every (sql, params) that hits the DB
    sql_calls = []

    def _exec(stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        sql_calls.append(sql)
        mock = MagicMock()
        mock.fetchone.return_value = (0,)
        return mock

    db = MagicMock()
    db.execute.side_effect = _exec

    _run(
        mgr.anonymize_audit_logs_for_user(
            db=db, user_id=USER, tenant_id=TENANT, actor=_actor(),
        )
    )

    for sql in sql_calls:
        upper = sql.upper()
        assert "UPDATE AUDIT_LOGS" not in upper, (
            f"Per-user anonymization must not UPDATE audit_logs: {sql}"
        )
        assert "DELETE FROM AUDIT_LOGS" not in upper, (
            f"Per-user anonymization must not DELETE audit_logs: {sql}"
        )


@pytest.mark.security
def test_anonymize_for_user_handles_db_error_gracefully():
    """If the blast-radius SELECT fails, the method returns (0, 1)
    instead of raising — the caller decides whether a downstream error
    should fail the erasure.  Keeping this contract matches
    ``anonymize_audit_logs``'s existing tuple-return shape."""
    mgr = _manager()
    db = MagicMock()
    db.execute.side_effect = RuntimeError("connection reset")

    records_affected, errors = _run(
        mgr.anonymize_audit_logs_for_user(
            db=db, user_id=USER, tenant_id=TENANT, actor=_actor(),
        )
    )
    assert records_affected == 0
    assert errors == 1


@pytest.mark.security
def test_anonymize_for_user_does_not_target_retention_threshold():
    """Regression guard: the per-user method must NOT be implemented by
    delegating to ``anonymize_audit_logs`` (which filters by retention
    threshold).  If anyone refactors the per-user method into a thin
    wrapper around the batch method, this test surfaces it.

    We assert the SQL issued by the per-user method does not carry a
    ``timestamp <`` predicate.
    """
    mgr = _manager()
    db = _db_with_count(count=5)

    _run(
        mgr.anonymize_audit_logs_for_user(
            db=db, user_id=USER, tenant_id=TENANT, actor=_actor(),
        )
    )

    sql_arg, _ = db.execute.call_args.args
    sql = str(sql_arg)
    assert "timestamp <" not in sql, (
        "Per-user anonymization must not filter by retention threshold; "
        "it is user-scoped, not time-scoped."
    )
