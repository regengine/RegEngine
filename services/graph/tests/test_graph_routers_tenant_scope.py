"""Tenant scoping tests for graph-service routers.

Covers issue #1244 (recall). The #1236 (audit) and #1242 (drift) tests
were removed together with the unreachable routers/fsma/audit.py and
fsma_drift.py modules (dead-code sweep).

Each endpoint must derive `tenant_id` from the authenticated request
context (via `Depends(get_current_tenant_id)`), never from the query
string, and must never return records belonging to other tenants.

Tests exercise the route handlers directly (bypassing middleware) so
they can assert on the handler signatures and the post-query tenant
filtering logic.  Neo4j and SQLAlchemy sessions are mocked.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.fsma_audit import reset_audit_log
from services.graph.app.routers.fsma import recall as recall_router

TENANT_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = uuid.UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset the audit log so tests are independent."""
    reset_audit_log()
    yield
    reset_audit_log()


# ── #1244 — recall history/drill endpoints must source tenant from auth ─────


class TestRecallHistoryTenantScope:
    """#1244 — recall endpoints must not trust query-param tenant_id."""

    def test_recall_history_signature_rejects_query_tenant_id(self):
        import inspect

        sig = inspect.signature(recall_router.get_recall_history)
        assert "tenant_id" in sig.parameters
        default = sig.parameters["tenant_id"].default
        assert hasattr(default, "dependency")
        assert default.dependency.__name__ == "get_current_tenant_id"

    def test_recall_history_only_returns_caller_tenant(self):
        from datetime import datetime, timezone

        from services.graph.app.fsma_recall import (
            RecallDrill,
            RecallSeverity,
            RecallType,
        )

        drill_a = RecallDrill(
            drill_id="drill_a_0000000001",
            tenant_id=str(TENANT_A),
            created_at=datetime.now(timezone.utc),
            drill_type=RecallType.FORWARD_TRACE,
            severity=RecallSeverity.CLASS_II,
        )
        fake_engine = MagicMock()
        fake_engine.get_drill_history.return_value = [drill_a]

        with patch.object(recall_router, "get_recall_engine", return_value=fake_engine):
            resp = recall_router.get_recall_history(limit=20, tenant_id=TENANT_A, api_key={"tenant_id": "irrelevant"})
        fake_engine.get_drill_history.assert_called_once_with(str(TENANT_A), limit=20)
        assert resp["drills"][0]["tenant_id"] == str(TENANT_A)

    def test_recall_history_raises_on_cross_tenant_leak(self):
        from datetime import datetime, timezone

        from services.graph.app.fsma_recall import (
            RecallDrill,
            RecallSeverity,
            RecallType,
        )

        leaky = RecallDrill(
            drill_id="drill_leak_00000001",
            tenant_id=str(TENANT_B),
            created_at=datetime.now(timezone.utc),
            drill_type=RecallType.FORWARD_TRACE,
            severity=RecallSeverity.CLASS_II,
        )
        fake_engine = MagicMock()
        fake_engine.get_drill_history.return_value = [leaky]

        with patch.object(recall_router, "get_recall_engine", return_value=fake_engine):
            with pytest.raises(HTTPException) as exc_info:
                recall_router.get_recall_history(limit=20, tenant_id=TENANT_A, api_key={"tenant_id": str(TENANT_A)})
            assert exc_info.value.status_code == 500
            assert "invariant violation" in exc_info.value.detail

    def test_drill_detail_blocks_cross_tenant_access(self):
        from datetime import datetime, timezone

        from services.graph.app.fsma_recall import (
            RecallDrill,
            RecallSeverity,
            RecallType,
        )

        other_tenant_drill = RecallDrill(
            drill_id="drill_other_tenant01",
            tenant_id=str(TENANT_B),
            created_at=datetime.now(timezone.utc),
            drill_type=RecallType.FORWARD_TRACE,
            severity=RecallSeverity.CLASS_II,
        )
        fake_engine = MagicMock()
        fake_engine.get_drill.return_value = other_tenant_drill

        with patch.object(recall_router, "get_recall_engine", return_value=fake_engine):
            with pytest.raises(HTTPException) as exc_info:
                recall_router.get_drill_details(
                    drill_id="drill_other_tenant01",
                    tenant_id=TENANT_A,
                    api_key={},
                )
            assert exc_info.value.status_code == 404

    def test_drill_cancel_blocks_cross_tenant_access(self):
        from datetime import datetime, timezone

        from services.graph.app.fsma_recall import (
            RecallDrill,
            RecallSeverity,
            RecallType,
        )

        other_tenant_drill = RecallDrill(
            drill_id="drill_other_cancel01",
            tenant_id=str(TENANT_B),
            created_at=datetime.now(timezone.utc),
            drill_type=RecallType.FORWARD_TRACE,
            severity=RecallSeverity.CLASS_II,
        )
        fake_engine = MagicMock()
        fake_engine.get_drill.return_value = other_tenant_drill

        with patch.object(recall_router, "get_recall_engine", return_value=fake_engine):
            with pytest.raises(HTTPException) as exc_info:
                recall_router.cancel_recall_drill(
                    drill_id="drill_other_cancel01",
                    tenant_id=TENANT_A,
                    api_key={},
                )
            assert exc_info.value.status_code == 404
        fake_engine.cancel_drill.assert_not_called()


class TestRecallSchedulesTenantScope:
    """#1244 — schedule list/create must come from auth tenant."""

    def test_schedules_signature_has_tenant_dependency(self):
        import inspect

        sig = inspect.signature(recall_router.get_recall_schedules)
        default = sig.parameters["tenant_id"].default
        assert hasattr(default, "dependency")
        assert default.dependency.__name__ == "get_current_tenant_id"

        sig2 = inspect.signature(recall_router.create_recall_schedule)
        default2 = sig2.parameters["tenant_id"].default
        assert hasattr(default2, "dependency")
        assert default2.dependency.__name__ == "get_current_tenant_id"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
