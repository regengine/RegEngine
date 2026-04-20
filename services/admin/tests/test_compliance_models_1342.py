"""
Regression coverage for ``app/compliance_models.py`` — closes the 77% gap.

All uncovered lines are methods on SQLAlchemy model classes:
* ``TenantComplianceStatusModel.__repr__`` (line 109)
* ``TenantComplianceStatusModel.to_dict`` — the ``next_deadline``
  countdown-seconds branch and the None branch (lines 113-124)
* ``TenantComplianceStatusModel._get_status_emoji`` (line 140)
* ``TenantComplianceStatusModel._get_status_label`` (line 147)
* ``ComplianceAlertModel.__repr__`` (line 210)
* ``ComplianceAlertModel.to_dict`` — the active-countdown branch and
  the expired branch (lines 214-231)
* ``ComplianceAlertModel._get_severity_emoji`` (line 257)
* ``TenantProductProfileModel.to_dict`` (line 326)

None of these methods touch the DB; they operate purely on already-
hydrated Python attributes — tested without SQLAlchemy sessions or
migrations.

Tracks GitHub issue #1342.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from unittest.mock import MagicMock
import pytest

service_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("sqlalchemy")

from app.compliance_models import (  # noqa: E402
    AlertSeverity,
    ComplianceAlertModel,
    ComplianceStatus,
    TenantComplianceStatusModel,
    TenantProductProfileModel,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_TID = uuid.UUID("00000000-0000-0000-0000-000000000001")
_AID = uuid.UUID("00000000-0000-0000-0000-000000000002")
_NOW = datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc)


def _status_model(**kwargs) -> TenantComplianceStatusModel:
    m = MagicMock(spec=TenantComplianceStatusModel)
    m._get_status_emoji = TenantComplianceStatusModel._get_status_emoji.__get__(m)
    m._get_status_label = TenantComplianceStatusModel._get_status_label.__get__(m)
    m.to_dict = TenantComplianceStatusModel.to_dict.__get__(m)
    defaults = dict(
        tenant_id=_TID,
        status=ComplianceStatus.COMPLIANT.value,
        active_alert_count=0,
        critical_alert_count=0,
        completeness_score=1.0,
        last_status_change=None,
        next_deadline=None,
        next_deadline_description=None,
        created_at=_NOW,
        updated_at=_NOW,
    )
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


def _alert_model(**kwargs) -> ComplianceAlertModel:
    m = MagicMock(spec=ComplianceAlertModel)
    # attach the methods we want to call as real (not mocked)
    m._get_severity_emoji = ComplianceAlertModel._get_severity_emoji.__get__(m)
    m.to_dict = ComplianceAlertModel.to_dict.__get__(m)
    defaults = dict(
        id=_AID,
        tenant_id=_TID,
        source_type="FDA_RECALL",
        source_id="R-001",
        title="Test recall",
        summary="Summary",
        severity=AlertSeverity.HIGH.value,
        countdown_start=None,
        countdown_end=None,
        countdown_hours=None,
        required_actions=None,
        status="active",
        acknowledged_at=None,
        acknowledged_by=None,
        resolved_at=None,
        resolved_by=None,
        match_reason="product match",
        created_at=_NOW,
        updated_at=_NOW,
    )
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


def _product_profile(**kwargs) -> TenantProductProfileModel:
    m = MagicMock(spec=TenantProductProfileModel)
    m.to_dict = TenantProductProfileModel.to_dict.__get__(m)
    defaults = dict(
        tenant_id=_TID,
        product_categories=["leafy_greens"],
        supply_regions=["CA"],
        supplier_identifiers=["SUP-1"],
        fda_product_codes=["PC001"],
        retailer_relationships=["WFM"],
        created_at=_NOW,
        updated_at=_NOW,
    )
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


# ---------------------------------------------------------------------------
# TenantComplianceStatusModel — lines 109, 113-124, 140, 147
# ---------------------------------------------------------------------------


class TestTenantComplianceStatusToDict:

    def test_to_dict_without_next_deadline(self):
        """Lines 113-124 (False branch): when next_deadline is None the
        countdown fields must be None — a countdown display of '0h 0m'
        would be misleading for tenants with no upcoming deadline."""
        m = _status_model(status=ComplianceStatus.COMPLIANT.value)
        d = m.to_dict()
        assert d["countdown_seconds"] is None
        assert d["countdown_display"] is None
        assert d["next_deadline"] is None
        assert d["tenant_id"] == str(_TID)

    def test_to_dict_with_future_next_deadline_computes_countdown(self):
        """Lines 117-122 (True branch): next_deadline set to a future
        timestamp produces positive countdown_seconds and a formatted
        'Xh Ym' countdown_display string."""
        future = datetime.now(timezone.utc) + timedelta(hours=3, minutes=30)
        m = _status_model(next_deadline=future)
        d = m.to_dict()
        assert d["countdown_seconds"] is not None
        assert d["countdown_seconds"] > 0
        assert "h" in d["countdown_display"]
        assert "m" in d["countdown_display"]
        assert d["next_deadline"] == future.isoformat()

    def test_to_dict_status_fields_present(self):
        """Spot-check that status_emoji and status_label are included in
        the response dict (they call the helper methods below)."""
        m = _status_model(status=ComplianceStatus.NON_COMPLIANT.value)
        d = m.to_dict()
        assert "status_emoji" in d
        assert "status_label" in d
        assert d["status"] == ComplianceStatus.NON_COMPLIANT.value


class TestTenantComplianceStatusHelpers:

    def test_get_status_emoji_known_values(self):
        """Line 140: each ComplianceStatus maps to a known emoji; an
        unknown status falls back to ❓ so the UI never crashes."""
        for status, expected_emoji in [
            (ComplianceStatus.COMPLIANT.value, "✅"),
            (ComplianceStatus.AT_RISK.value, "⚠️"),
            (ComplianceStatus.NON_COMPLIANT.value, "🚨"),
        ]:
            m = _status_model(status=status)
            assert m._get_status_emoji() == expected_emoji

    def test_get_status_emoji_unknown_falls_back(self):
        """Line 144 .get default: unknown status → ❓."""
        m = _status_model(status="UNKNOWN_STATUS")
        assert m._get_status_emoji() == "❓"

    def test_get_status_label_known_values(self):
        """Line 147: each ComplianceStatus maps to a human-readable
        label. Pin so a re-ordering of the dict can't silently swap
        'At Risk' and 'Non-Compliant'."""
        for status, expected_label in [
            (ComplianceStatus.COMPLIANT.value, "Compliant"),
            (ComplianceStatus.AT_RISK.value, "At Risk"),
            (ComplianceStatus.NON_COMPLIANT.value, "Non-Compliant"),
        ]:
            m = _status_model(status=status)
            assert m._get_status_label() == expected_label

    def test_get_status_label_unknown_falls_back(self):
        """Line 151 .get default: unknown status → 'Unknown'."""
        m = _status_model(status="MYSTERY")
        assert m._get_status_label() == "Unknown"


# ---------------------------------------------------------------------------
# ComplianceAlertModel — lines 210, 214-231, 257
# ---------------------------------------------------------------------------


class TestComplianceAlertToDict:

    def test_to_dict_without_countdown_end(self):
        """Lines 214-216 (False branch): no countdown_end → countdown_seconds
        defaults to 0, countdown_display to 'Expired', is_expired False.
        Alerts without a countdown (e.g. informational alerts) must not
        display a misleading timer."""
        m = _alert_model(countdown_end=None)
        d = m.to_dict()
        assert d["countdown_seconds"] == 0
        assert d["countdown_display"] == "Expired"
        assert d["is_expired"] is False
        assert d["id"] == str(_AID)

    def test_to_dict_active_countdown(self):
        """Lines 223-226 (True branch): countdown_end in the future →
        positive countdown_seconds and formatted 'Xh Ym Zs' display.
        Pinned so a refactor that accidentally drops seconds from the
        display gets caught."""
        m = _alert_model(countdown_end=datetime.now(timezone.utc) + timedelta(hours=2, minutes=15, seconds=10))
        d = m.to_dict()
        assert d["countdown_seconds"] > 0
        assert "h" in d["countdown_display"]
        assert "m" in d["countdown_display"]
        assert "s" in d["countdown_display"]
        assert d["is_expired"] is False

    def test_to_dict_expired_countdown(self):
        """Lines 228-229 (False branch): countdown_end in the past →
        countdown_seconds == 0, is_expired True. This is what triggers
        the 'OVERDUE' badge in the UI — must not regress."""
        m = _alert_model(countdown_end=_NOW - timedelta(hours=1))
        d = m.to_dict()
        assert d["countdown_seconds"] == 0
        assert d["is_expired"] is True

    def test_to_dict_required_actions_defaults_to_empty_list(self):
        """Line 246: ``required_actions or []`` — None in the DB must
        come back as [] not None so the frontend can always iterate."""
        m = _alert_model(required_actions=None)
        d = m.to_dict()
        assert d["required_actions"] == []

    def test_to_dict_optional_timestamp_fields_none(self):
        """Timestamp fields (acknowledged_at, resolved_at, etc.) with
        None values must serialize as None, not crash on .isoformat()."""
        m = _alert_model(
            acknowledged_at=None,
            resolved_at=None,
            countdown_start=None,
            countdown_end=None,
            created_at=None,
        )
        d = m.to_dict()
        assert d["acknowledged_at"] is None
        assert d["resolved_at"] is None
        assert d["countdown_start"] is None
        assert d["created_at"] is None


class TestComplianceAlertSeverityEmoji:

    def test_all_known_severities_have_emoji(self):
        """Line 257: each AlertSeverity maps to a distinct emoji."""
        expected = {
            AlertSeverity.CRITICAL.value: "🚨",
            AlertSeverity.HIGH.value: "⚠️",
            AlertSeverity.MEDIUM.value: "📋",
            AlertSeverity.LOW.value: "ℹ️",
        }
        for severity, emoji in expected.items():
            m = _alert_model(severity=severity)
            assert m._get_severity_emoji() == emoji

    def test_unknown_severity_falls_back(self):
        """Line 262 .get default: unknown severity → ❓."""
        m = _alert_model(severity="ULTRA_CRITICAL")
        assert m._get_severity_emoji() == "❓"


# ---------------------------------------------------------------------------
# TenantProductProfileModel — line 326
# ---------------------------------------------------------------------------


class TestTenantProductProfileToDict:

    def test_to_dict_returns_all_fields(self):
        """Line 326: to_dict on TenantProductProfile must serialize all
        five JSON list columns. The tenant_id is stringified (UUID →
        str) for API consumption."""
        m = _product_profile()
        d = m.to_dict()
        assert d["tenant_id"] == str(_TID)
        assert d["product_categories"] == ["leafy_greens"]
        assert d["supply_regions"] == ["CA"]
        assert d["supplier_identifiers"] == ["SUP-1"]
        assert d["fda_product_codes"] == ["PC001"]
        assert d["retailer_relationships"] == ["WFM"]

    def test_to_dict_null_lists_default_to_empty(self):
        """Line 328-332 ``or []``: None columns (e.g. newly-inserted
        rows before backfill) must come back as [] so callers can always
        iterate without a None-check."""
        m = _product_profile(
            product_categories=None,
            supply_regions=None,
            supplier_identifiers=None,
            fda_product_codes=None,
            retailer_relationships=None,
        )
        d = m.to_dict()
        assert d["product_categories"] == []
        assert d["supply_regions"] == []
        assert d["supplier_identifiers"] == []
        assert d["fda_product_codes"] == []
        assert d["retailer_relationships"] == []
