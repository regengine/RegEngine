"""Regression tests for #1399 — soft_delete_record missing tenant scoping.

Before the fix, ``DataRetentionManager.soft_delete_record`` issued
``UPDATE <resource_type> SET deleted_at=... WHERE id=:record_id`` with no
tenant predicate. Any caller that accepted an attacker-influenced
``record_id`` produced a cross-tenant soft-delete. These tests lock in
the tenant predicate:

- ``tenant_id`` is required for tenant-scoped resources.
- The generated UPDATE SQL includes ``tenant_id = :tenant_id`` for
  scoped resources.
- Global resources (``user_account``) skip the predicate.
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.data_retention import (
    DataRetentionManager,
    DeletionRequest,
    RetentionPolicy,
    _is_tenant_scoped,
    _GLOBAL_RESOURCES,
)
from shared.audit_logging import AuditActor


TENANT = uuid.uuid4()


def _manager():
    mgr = DataRetentionManager(audit_logger=MagicMock())
    # Short-circuit audit writes so the mocked DB doesn't need a real audit table.
    mgr.audit_logger.log_data_modification = AsyncMock(return_value=None)
    mgr.audit_logger.log = AsyncMock(return_value=None)
    return mgr


def _db_with_rowcount(rowcount: int = 1):
    db = MagicMock()
    result = MagicMock()
    result.rowcount = rowcount
    db.execute.return_value = result
    return db


def _actor():
    return AuditActor(actor_type="user", actor_id=str(uuid.uuid4()))


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.mark.security
def test_tenant_scoped_resource_requires_tenant_id():
    """Calling soft_delete_record on a scoped resource without tenant_id raises."""
    mgr = _manager()
    with pytest.raises(ValueError, match="tenant_id is required"):
        _run(
            mgr.soft_delete_record(
                db=_db_with_rowcount(),
                resource_type="supplier_contact",
                record_id=str(uuid.uuid4()),
                policy=RetentionPolicy.SUPPLIER_CONTACT,
                deletion_request=DeletionRequest.USER_INITIATED,
                actor=_actor(),
                tenant_id=None,
            )
        )


@pytest.mark.security
def test_tenant_scoped_update_includes_tenant_predicate():
    """UPDATE for a scoped resource carries 'tenant_id = :tenant_id'."""
    mgr = _manager()
    db = _db_with_rowcount()
    record_id = str(uuid.uuid4())

    _run(
        mgr.soft_delete_record(
            db=db,
            resource_type="supplier_contact",
            record_id=record_id,
            policy=RetentionPolicy.SUPPLIER_CONTACT,
            deletion_request=DeletionRequest.USER_INITIATED,
            actor=_actor(),
            tenant_id=TENANT,
        )
    )

    assert db.execute.called
    sql_arg, params = db.execute.call_args.args
    sql = str(sql_arg)
    assert "tenant_id = :tenant_id" in sql
    assert params["tenant_id"] == str(TENANT)
    assert params["record_id"] == record_id


@pytest.mark.security
def test_global_resource_skips_tenant_predicate():
    """UPDATE for user_account (global) does NOT include tenant_id filter."""
    mgr = _manager()
    db = _db_with_rowcount()

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

    sql_arg, params = db.execute.call_args.args
    sql = str(sql_arg)
    assert "tenant_id" not in sql
    assert "tenant_id" not in params


@pytest.mark.security
def test_process_deletion_request_forwards_tenant_id():
    """The higher-level process_deletion_request must pass tenant_id through."""
    mgr = _manager()
    db = _db_with_rowcount()
    record_id = str(uuid.uuid4())

    _run(
        mgr.process_deletion_request(
            db=db,
            resource_type="supplier_contact",
            record_id=record_id,
            policy=RetentionPolicy.SUPPLIER_CONTACT,
            deletion_request=DeletionRequest.USER_INITIATED,
            actor=_actor(),
            tenant_id=TENANT,
        )
    )

    sql_arg, params = db.execute.call_args.args
    assert "tenant_id = :tenant_id" in str(sql_arg)
    assert params["tenant_id"] == str(TENANT)


def test_global_resource_set_contains_user_account():
    """user_account must remain in the global set — else the erasure path breaks."""
    assert "user_account" in _GLOBAL_RESOURCES
    assert not _is_tenant_scoped("user_account")
    assert _is_tenant_scoped("supplier_contact")
