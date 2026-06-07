"""Tests for session scope tenant isolation with transaction-scoped set_config.

These tests verify the psycopg3/asyncpg-compatible tenant GUC helper.
The session scope now relies on ``SELECT set_config('app.tenant_id', :tid, true)``
so the tenant binding remains parameterized and transaction-scoped.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


class TestSessionScopeTenantIsolation:
    """Tests for _session_scope tenant isolation behavior."""

    def test_session_scope_sets_tenant_context_with_valid_uuid(self):
        """Verify the tenant GUC is set with a parameterized UUID binding."""
        from services.admin.app.metrics import HallucinationTracker

        # Create a mock session that captures executed SQL
        executed_calls = []

        class MockSession:
            def execute(self, stmt, params=None):
                executed_calls.append((str(stmt), params))

            def commit(self):
                pass

            def rollback(self):
                pass

            def close(self):
                pass

        def session_factory():
            return MockSession()

        tracker = HallucinationTracker(session_factory, None)
        tenant_id = str(uuid4())

        # Use the session scope with a tenant_id
        with tracker._session_scope(tenant_id=tenant_id) as session:
            pass

        # Verify set_config was called with the tenant_id binding
        assert len(executed_calls) == 1
        sql, params = executed_calls[0]
        assert "set_config" in sql
        assert "'app.tenant_id'" in sql
        assert "true" in sql.lower()
        assert params == {"tid": tenant_id}

    def test_session_scope_no_set_without_tenant_id(self):
        """Verify the tenant GUC is not set when tenant_id is None."""
        from services.admin.app.metrics import HallucinationTracker

        executed_statements = []

        class MockSession:
            def execute(self, stmt, params=None):
                executed_statements.append((str(stmt), params))

            def commit(self):
                pass

            def rollback(self):
                pass

            def close(self):
                pass

        def session_factory():
            return MockSession()

        tracker = HallucinationTracker(session_factory, None)

        # Use the session scope without a tenant_id
        with tracker._session_scope(tenant_id=None) as session:
            pass

        # Verify no SET LOCAL was executed
        assert len(executed_statements) == 0

    def test_session_scope_rollbacks_on_exception(self):
        """Verify session rollback is called when an exception occurs."""
        from services.admin.app.metrics import HallucinationTracker

        rollback_called = False
        close_called = False

        class MockSession:
            def execute(self, stmt):
                pass

            def commit(self):
                raise RuntimeError("Simulated commit failure")

            def rollback(self):
                nonlocal rollback_called
                rollback_called = True

            def close(self):
                nonlocal close_called
                close_called = True

        def session_factory():
            return MockSession()

        tracker = HallucinationTracker(session_factory, None)

        with pytest.raises(RuntimeError, match="Simulated commit failure"):
            with tracker._session_scope() as session:
                pass

        assert rollback_called, "Session should be rolled back on exception"
        assert close_called, "Session should be closed after exception"

    def test_session_scope_closes_session_on_success(self):
        """Verify session is properly closed after successful operations."""
        from services.admin.app.metrics import HallucinationTracker

        close_called = False
        commit_called = False

        class MockSession:
            def execute(self, stmt):
                pass

            def commit(self):
                nonlocal commit_called
                commit_called = True

            def rollback(self):
                pass

            def close(self):
                nonlocal close_called
                close_called = True

        def session_factory():
            return MockSession()

        tracker = HallucinationTracker(session_factory, None)

        with tracker._session_scope() as session:
            pass

        assert commit_called, "Session should be committed on success"
        assert close_called, "Session should be closed after completion"


class TestTenantIdValidation:
    """Tests for tenant_id format validation in session scope."""

    def test_tenant_id_uuid_format_preserved(self):
        """Verify UUID format is preserved in the tenant binding."""
        from services.admin.app.metrics import HallucinationTracker

        captured_call = None

        class MockSession:
            def execute(self, stmt, params=None):
                nonlocal captured_call
                captured_call = (str(stmt), params)

            def commit(self):
                pass

            def rollback(self):
                pass

            def close(self):
                pass

        def session_factory():
            return MockSession()

        tracker = HallucinationTracker(session_factory, None)

        # Standard UUID format
        tenant_id = "550e8400-e29b-41d4-a716-446655440000"

        with tracker._session_scope(tenant_id=tenant_id) as session:
            pass

        # Verify the UUID is preserved in the parameterized binding
        assert captured_call is not None
        sql, params = captured_call
        assert "set_config" in sql
        assert params == {"tid": tenant_id}

    def test_session_scope_sql_injection_protection(self):
        """
        Verify that tenant_id is safely handled.

        Note: In production, tenant_id should be validated as a UUID before
        reaching this point. The helper now uses a parameterized binding
        rather than interpolating the value into SQL text.
        """
        from services.admin.app.metrics import HallucinationTracker

        captured_call = None

        class MockSession:
            def execute(self, stmt, params=None):
                nonlocal captured_call
                captured_call = (str(stmt), params)

            def commit(self):
                pass

            def rollback(self):
                pass

            def close(self):
                pass

        def session_factory():
            return MockSession()

        tracker = HallucinationTracker(session_factory, None)

        # This should be a valid UUID in production
        tenant_id = "550e8400-e29b-41d4-a716-446655440000"

        with tracker._session_scope(tenant_id=tenant_id) as session:
            pass

        # Verify statement format and parameterized binding
        assert captured_call is not None
        sql, params = captured_call
        assert "set_config" in sql
        assert params == {"tid": tenant_id}
