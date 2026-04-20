"""
Tests for issue #1412: tenant erasure must purge Neo4j subgraph.

After the Postgres soft-delete commits, the erasure route must call
``supplier_graph_sync.purge_tenant(tenant_id)`` when
``ENABLE_NEO4J_TENANT_PURGE=true``.  When the flag is absent or false,
Neo4j must not be touched.  A Neo4j failure must not roll back the
Postgres erasure (soft-fail).
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

TENANT_ID = str(uuid.uuid4())
USER_ID = str(uuid.uuid4())

_CURRENT_USER = {
    "user_id": USER_ID,
    "tenant_id": TENANT_ID,
    "email": "user@example.com",
}


def _make_body(confirm=True, reason="gdpr test"):
    b = MagicMock()
    b.confirm = confirm
    b.reason = reason
    return b


def _make_fake_db_ctx():
    """Return a context manager that yields a MagicMock session."""
    fake_db = MagicMock()
    fake_db.commit = MagicMock()
    fake_db.flush = MagicMock()
    fake_db.add = MagicMock()

    @contextmanager
    def _ctx():
        yield fake_db

    return _ctx


def _make_shared_modules():
    """Patch shared.* lazy-imported inside the route body."""
    fake_drm = MagicMock()
    fake_drm.process_deletion_request = AsyncMock(
        return_value={
            "soft_deleted": True,
            "hard_delete_scheduled": True,
            "hard_delete_date": "2027-01-01",
        }
    )
    fake_drm.anonymize_audit_logs_for_user = AsyncMock(return_value=(1, 0))

    fake_retention = MagicMock()
    fake_retention.DataRetentionManager.return_value = fake_drm
    fake_retention.DeletionRequest.USER_INITIATED = "USER_INITIATED"

    class _FakePolicy:
        USER_ACCOUNT = "user_account"

    fake_retention.RetentionPolicy = _FakePolicy

    fake_audit_logging = MagicMock()
    fake_audit_logging.AuditActor = MagicMock(side_effect=lambda **kw: kw)

    fake_pii = MagicMock()
    fake_pii.mask_email.side_effect = lambda e: f"***@{e.split('@')[-1]}"

    return fake_retention, fake_audit_logging, fake_pii


# ---------------------------------------------------------------------------
# Core helper that runs the route under full patches
# ---------------------------------------------------------------------------

async def _run_erasure(*, flag: str | None, graph_sync: MagicMock) -> tuple:
    """
    Execute ``request_erasure`` with all external deps mocked.

    Returns (response, audit_logger_mock).
    """
    fake_retention, fake_audit_logging, fake_pii = _make_shared_modules()
    db_ctx = _make_fake_db_ctx()
    mock_audit = MagicMock()

    env_patch = {}
    if flag is not None:
        env_patch["ENABLE_NEO4J_TENANT_PURGE"] = flag

    import os
    # Make sure the flag is absent when we want unset behaviour
    remove_flag = flag is None

    mock_logger = MagicMock()

    with (
        patch.dict("os.environ", env_patch, clear=False),
        patch("shared.data_retention", fake_retention, create=True),
        patch("shared.audit_logging", fake_audit_logging, create=True),
        patch("shared.pii", fake_pii, create=True),
        patch("app.erasure_routes.supplier_graph_sync", graph_sync),
        patch("app.erasure_routes.get_db", db_ctx),
        patch("app.erasure_routes.AuditLogger", mock_audit),
        patch("app.erasure_routes.logger", mock_logger),
        # Patch the lazy imports inside the function body
        patch.dict(
            "sys.modules",
            {
                "shared.data_retention": fake_retention,
                "shared.audit_logging": fake_audit_logging,
                "shared.pii": fake_pii,
            },
        ),
    ):
        if remove_flag:
            os.environ.pop("ENABLE_NEO4J_TENANT_PURGE", None)

        from app.erasure_routes import request_erasure

        response = await request_erasure(
            body=_make_body(),
            current_user=_CURRENT_USER,
        )

    return response, mock_audit


# ---------------------------------------------------------------------------
# Test: flag TRUE → purge_tenant is called, count propagates to response
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_purge_called_when_flag_true():
    """purge_tenant must be called when ENABLE_NEO4J_TENANT_PURGE=true."""
    graph_sync = MagicMock()
    graph_sync.purge_tenant.return_value = 42

    response, _ = await _run_erasure(flag="true", graph_sync=graph_sync)

    graph_sync.purge_tenant.assert_called_once_with(TENANT_ID)
    assert response.neo4j_nodes_purged == 42


# ---------------------------------------------------------------------------
# Test: flag FALSE → purge_tenant NOT called
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_purge_not_called_when_flag_false():
    """purge_tenant must NOT be called when ENABLE_NEO4J_TENANT_PURGE=false."""
    graph_sync = MagicMock()
    graph_sync.purge_tenant.return_value = 0

    response, _ = await _run_erasure(flag="false", graph_sync=graph_sync)

    graph_sync.purge_tenant.assert_not_called()
    assert response.neo4j_nodes_purged == 0


# ---------------------------------------------------------------------------
# Test: flag unset → purge_tenant NOT called
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_purge_not_called_when_flag_unset():
    """purge_tenant must NOT be called when ENABLE_NEO4J_TENANT_PURGE is absent."""
    graph_sync = MagicMock()
    graph_sync.purge_tenant.return_value = 0

    response, _ = await _run_erasure(flag=None, graph_sync=graph_sync)

    graph_sync.purge_tenant.assert_not_called()
    assert response.neo4j_nodes_purged == 0


# ---------------------------------------------------------------------------
# Test: Neo4j raises → erasure still returns 200 (soft-fail)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_neo4j_failure_does_not_fail_erasure():
    """A Neo4j error must not cause the endpoint to raise; Postgres erasure committed."""
    graph_sync = MagicMock()
    graph_sync.purge_tenant.side_effect = ConnectionError("neo4j is down")

    response, _ = await _run_erasure(flag="true", graph_sync=graph_sync)

    assert response.status == "accepted"
    assert response.neo4j_nodes_purged == 0


# ---------------------------------------------------------------------------
# Test: audit event recorded when purge succeeds
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_event_recorded_on_purge():
    """AuditLogger.log_event must be called with action='tenant.neo4j_purge'."""
    graph_sync = MagicMock()
    graph_sync.purge_tenant.return_value = 7

    response, mock_audit = await _run_erasure(flag="true", graph_sync=graph_sync)

    assert response.neo4j_nodes_purged == 7

    calls = mock_audit.log_event.call_args_list
    purge_calls = [
        c for c in calls
        if c.kwargs.get("action") == "tenant.neo4j_purge"
    ]
    assert purge_calls, (
        f"Expected log_event(action='tenant.neo4j_purge') but calls were: {calls}"
    )
    # Verify metadata carries the deleted_nodes count
    meta = purge_calls[0].kwargs.get("metadata", {})
    assert meta.get("deleted_nodes") == 7


# ---------------------------------------------------------------------------
# Unit tests: SupplierGraphSync.purge_tenant directly
# ---------------------------------------------------------------------------

def test_purge_tenant_returns_deleted_count():
    """purge_tenant returns the count returned by the Cypher query."""
    from app.supplier_graph_sync import SupplierGraphSync, PURGE_TENANT_QUERY

    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.run.return_value.single.return_value = {"deleted": 15}
    mock_driver.session.return_value = mock_session

    sync = SupplierGraphSync(enabled=True, driver=mock_driver)
    result = sync.purge_tenant("test-tenant-abc")

    assert result == 15
    mock_session.run.assert_called_once_with(
        PURGE_TENANT_QUERY, {"tenant_id": "test-tenant-abc"}
    )


def test_purge_tenant_disabled_returns_zero():
    """purge_tenant returns 0 immediately when sync is disabled."""
    from app.supplier_graph_sync import SupplierGraphSync

    sync = SupplierGraphSync(enabled=False)
    assert sync.purge_tenant("any-tenant") == 0


def test_purge_tenant_idempotent_zero_match():
    """purge_tenant returns 0 when no nodes match (already purged / tenant never synced)."""
    from app.supplier_graph_sync import SupplierGraphSync

    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.run.return_value.single.return_value = {"deleted": 0}
    mock_driver.session.return_value = mock_session

    sync = SupplierGraphSync(enabled=True, driver=mock_driver)
    assert sync.purge_tenant("already-gone") == 0
