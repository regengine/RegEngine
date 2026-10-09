"""Regression test: scheduler error handler must not crash on unbound variable.

In ``ComplianceIntegration.process_enforcement_item`` the ``except`` handler
logged ``match["tenant_id"]``, but ``match`` is only assigned inside the
``try``. When ``_find_matching_tenants`` raised before ``match`` was bound,
the handler itself raised ``UnboundLocalError`` (not in the caught tuple),
aborting the whole batch. The fix initializes ``match`` before ``try`` and
falls back to the loop ``tenant_id`` in the handler.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError


def _make_item():
    from app.models import EnforcementItem, EnforcementSeverity, SourceType

    return EnforcementItem(
        source_type=SourceType.FDA_RECALL,
        source_id="fda_rec:err-handler-1",
        title="Test Recall",
        summary="lettuce contamination",
        url="https://example.test/recall/1",
        published_date=datetime.now(timezone.utc),
        severity=EnforcementSeverity.HIGH,
        affected_companies=["Acme Foods"],
        raw_data={"code_info": "LOT-A"},
    )


def test_error_before_match_does_not_abort_batch(monkeypatch):
    from app import compliance_integration as ci_module

    fake_settings = MagicMock()
    fake_settings.database_url = "sqlite:///:memory:"
    monkeypatch.setattr(ci_module, "get_settings", lambda: fake_settings)

    integration = ci_module.ComplianceIntegration()

    tenant_a = str(uuid4())
    tenant_b = str(uuid4())
    monkeypatch.setattr(ci_module, "list_maintenance_tenant_ids", lambda: [tenant_a, tenant_b])
    monkeypatch.setattr(ci_module, "set_tenant_guc", lambda session, tid: None)

    mock_session = MagicMock()
    session_ctx = MagicMock()
    session_ctx.__enter__.return_value = mock_session
    session_ctx.__exit__.return_value = False
    integration.Session = MagicMock(return_value=session_ctx)

    # First tenant raises before ``match`` is ever bound; second has no match.
    with patch.object(
        integration,
        "_find_matching_tenants",
        side_effect=[SQLAlchemyError("db down"), []],
    ) as finder:
        result = integration.process_enforcement_item(_make_item())

    assert result == []
    assert finder.call_count == 2
    assert mock_session.rollback.call_count >= 1
