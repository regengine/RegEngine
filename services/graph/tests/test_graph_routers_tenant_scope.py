"""Tenant scoping tests for graph-service routers.

Covers issues #1236 (audit), #1242 (drift/suppliers), #1244 (recall).

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

from services.graph.app.routers.fsma import audit as audit_router
from services.graph.app.routers.fsma import recall as recall_router
from services.graph.app.fsma_audit import (
    FSMAAuditAction,
    FSMAAuditEntry,
    reset_audit_log,
    get_audit_log,
)
from services.graph.app.fsma_drift import (
    AlertSeverity,
    AlertType,
    DriftAlert,
    get_drift_detector,
    reset_drift_detector,
)


TENANT_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = uuid.UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset audit log and drift detector so tests are independent."""
    reset_audit_log()
    reset_drift_detector()
    yield
    reset_audit_log()
    reset_drift_detector()


# ── #1236 — audit endpoints must source tenant from auth ─────────────────────


class TestAuditTenantScope:
    """#1236 — audit endpoints must not accept query-param tenant_id."""

    def test_get_full_audit_log_signature_rejects_query_tenant_id(self):
        """The endpoint signature must not accept `tenant_id` as a query param."""
        import inspect
        sig = inspect.signature(audit_router.get_full_audit_log)
        tenant_param = sig.parameters.get("tenant_id")
        assert tenant_param is not None
        default = tenant_param.default
        assert hasattr(default, "dependency"), (
            "tenant_id must be Depends(get_current_tenant_id), not Query(...)"
        )
        assert default.dependency.__name__ == "get_current_tenant_id"

    def test_get_audit_trail_signature_has_tenant_dependency(self):
        import inspect
        sig = inspect.signature(audit_router.get_audit_trail)
        assert "tenant_id" in sig.parameters
        default = sig.parameters["tenant_id"].default
        assert hasattr(default, "dependency")
        assert default.dependency.__name__ == "get_current_tenant_id"

    def test_get_audit_verify_signature_has_tenant_dependency(self):
        import inspect
        sig = inspect.signature(audit_router.verify_audit_integrity)
        assert "tenant_id" in sig.parameters
        default = sig.parameters["tenant_id"].default
        assert hasattr(default, "dependency")

    def test_get_full_audit_log_returns_only_caller_tenant(self):
        """Entries belonging to other tenants must not be returned."""
        log = get_audit_log()
        log.log(
            actor="tenant_a_user",
            action=FSMAAuditAction.EXTRACTED,
            target_type="Lot",
            target_id="LOT-A",
            tenant_id=str(TENANT_A),
        )
        log.log(
            actor="tenant_b_user",
            action=FSMAAuditAction.EXTRACTED,
            target_type="Lot",
            target_id="LOT-B",
            tenant_id=str(TENANT_B),
        )

        resp = audit_router.get_full_audit_log(
            action=None, tenant_id=TENANT_A, api_key="test-key"
        )
        for entry in resp["audit_trail"]:
            assert entry["tenant_id"] in (None, "", str(TENANT_A)), (
                f"cross-tenant entry leaked: {entry}"
            )

    def test_get_audit_trail_raises_on_cross_tenant_leak(self):
        """If the store returns a cross-tenant entry, raise 500 (invariant)."""
        entry = FSMAAuditEntry(
            actor="attacker",
            action=FSMAAuditAction.EXTRACTED,
            target_type="Lot",
            target_id="LOT-X",
            tenant_id=str(TENANT_B),
        )
        fake_log = MagicMock()
        fake_log.get_by_target.return_value = [entry]

        with patch.object(audit_router, "get_audit_log", return_value=fake_log):
            with pytest.raises(HTTPException) as exc_info:
                audit_router.get_audit_trail(
                    target_id="LOT-X", tenant_id=TENANT_A, api_key="test-key"
                )
            assert exc_info.value.status_code == 500
            assert "invariant violation" in exc_info.value.detail


# ── #1242 — drift and supplier health must scope per tenant ─────────────────


class TestDriftTenantScope:
    """#1242 — drift alerts and supplier health must be tenant-scoped."""

    def test_drift_status_signature_has_tenant_dependency(self):
        import inspect
        for fn_name in (
            "drift_monitoring_status",
            "analyze_drift",
            "get_drift_alerts",
            "get_supplier_health",
            "acknowledge_drift_alert",
            "resolve_drift_alert",
        ):
            fn = getattr(audit_router, fn_name)
            sig = inspect.signature(fn)
            assert "tenant_id" in sig.parameters, f"{fn_name} missing tenant_id"
            default = sig.parameters["tenant_id"].default
            assert hasattr(default, "dependency"), (
                f"{fn_name}: tenant_id must be Depends(...), got {default!r}"
            )

    def test_get_drift_alerts_filters_by_tenant(self):
        detector = get_drift_detector()
        alert_a = DriftAlert(
            alert_type=AlertType.KDE_COMPLETENESS_DROP,
            severity=AlertSeverity.WARNING,
            tenant_id=str(TENANT_A),
            message="tenant A alert",
        )
        alert_b = DriftAlert(
            alert_type=AlertType.KDE_COMPLETENESS_DROP,
            severity=AlertSeverity.WARNING,
            tenant_id=str(TENANT_B),
            message="tenant B alert",
        )
        with detector._lock:
            detector._alerts.append(alert_a)
            detector._alerts.append(alert_b)

        resp = audit_router.get_drift_alerts(
            status=None,
            severity=None,
            supplier_gln=None,
            limit=100,
            tenant_id=TENANT_A,
            api_key="test-key",
        )
        tenant_ids = {a["tenant_id"] for a in resp["alerts"]}
        assert str(TENANT_B) not in tenant_ids
        assert tenant_ids <= {str(TENANT_A), None, ""}

    def test_acknowledge_rejects_cross_tenant_alert(self):
        detector = get_drift_detector()
        alert_b = DriftAlert(
            alert_id="alert-cross-tenant",
            alert_type=AlertType.KDE_COMPLETENESS_DROP,
            severity=AlertSeverity.WARNING,
            tenant_id=str(TENANT_B),
        )
        with detector._lock:
            detector._alerts.append(alert_b)

        with pytest.raises(HTTPException) as exc_info:
            audit_router.acknowledge_drift_alert(
                alert_id="alert-cross-tenant",
                tenant_id=TENANT_A,
                api_key="test-key",
            )
        assert exc_info.value.status_code == 404

    def test_resolve_rejects_cross_tenant_alert(self):
        detector = get_drift_detector()
        alert_b = DriftAlert(
            alert_id="alert-cross-tenant-resolve",
            alert_type=AlertType.KDE_COMPLETENESS_DROP,
            severity=AlertSeverity.WARNING,
            tenant_id=str(TENANT_B),
        )
        with detector._lock:
            detector._alerts.append(alert_b)

        with pytest.raises(HTTPException) as exc_info:
            audit_router.resolve_drift_alert(
                alert_id="alert-cross-tenant-resolve",
                tenant_id=TENANT_A,
                api_key="test-key",
            )
        assert exc_info.value.status_code == 404


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
        from services.graph.app.fsma_recall import (
            RecallDrill, RecallType, RecallSeverity,
        )
        from datetime import datetime, timezone

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
            resp = recall_router.get_recall_history(
                limit=20, tenant_id=TENANT_A, api_key={"tenant_id": "irrelevant"}
            )
        fake_engine.get_drill_history.assert_called_once_with(str(TENANT_A), limit=20)
        assert resp["drills"][0]["tenant_id"] == str(TENANT_A)

    def test_recall_history_raises_on_cross_tenant_leak(self):
        from services.graph.app.fsma_recall import (
            RecallDrill, RecallType, RecallSeverity,
        )
        from datetime import datetime, timezone

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
                recall_router.get_recall_history(
                    limit=20, tenant_id=TENANT_A, api_key={"tenant_id": str(TENANT_A)}
                )
            assert exc_info.value.status_code == 500
            assert "invariant violation" in exc_info.value.detail

    def test_drill_detail_blocks_cross_tenant_access(self):
        from services.graph.app.fsma_recall import (
            RecallDrill, RecallType, RecallSeverity,
        )
        from datetime import datetime, timezone

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
        from services.graph.app.fsma_recall import (
            RecallDrill, RecallType, RecallSeverity,
        )
        from datetime import datetime, timezone

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
