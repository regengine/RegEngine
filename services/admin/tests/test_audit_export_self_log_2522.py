"""Regression coverage for #2522 — audit-export 'audit the auditor' self-log
must fail closed.

``/v1/audit/export`` records its own ``data.bulk.export`` entry via
``AuditLogger.log_event`` then ``db.commit()``. ``log_event`` is
best-effort: on failure (schema drift, an already-aborted transaction) it
swallows the error and returns ``None``. The endpoint discarded that
return value, so a privileged export — including a raw-PII release — could
return 200 with the data while its 'who exported what' record was silently
dropped.

These tests pin the fix (mirror of supplier_funnel_routes.py #1407):
* When the self-log returns ``None``, the export raises a 5xx and rolls
  back — it must NOT return 200 with entries.
* Happy path still returns 200 and persists exactly one
  ``data.bulk.export`` row carrying the declared purpose and
  ``raw_pii_released`` flag.

Tracks GitHub issue #2522.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

service_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("sqlalchemy")

from app import audit_routes  # noqa: E402
from app.audit import AuditLogger  # noqa: E402
from app.sqlalchemy_models import AuditLogModel  # noqa: E402
from fastapi import HTTPException  # noqa: E402

TENANT = UUID("00000000-0000-0000-0000-000000000099")
USER_ID = UUID("00000000-0000-0000-0000-000000000001")


def _stub_user():
    return SimpleNamespace(id=USER_ID, email="auditor@example.com", is_sysadmin=True)


def _run_export(db, **overrides):
    """Call the export route function directly with SQLite-backed session."""
    db.info["tenant_id"] = TENANT
    kwargs = dict(
        db=db,
        current_user=_stub_user(),
        purpose="compliance_investigation",
        start=None,
        end=None,
        event_category=None,
        severity=None,
        limit=10000,
        include_verification=False,
        include_pii=False,
    )
    kwargs.update(overrides)
    return audit_routes.export_audit_logs(**kwargs)


class TestExportSelfLogFailsClosed:
    def test_self_log_none_raises_5xx(self, db_session, monkeypatch):
        """If the self-log returns None, the export must be a 5xx, not a
        200 with entries (#2522)."""
        monkeypatch.setattr(AuditLogger, "log_event", staticmethod(lambda *a, **k: None))

        with pytest.raises(HTTPException) as exc_info:
            _run_export(db_session)

        assert exc_info.value.status_code == 500

    def test_self_log_none_rolls_back(self, db_session, monkeypatch):
        """On self-log failure the session is rolled back before the
        500 so no partial state is committed (#2522)."""
        monkeypatch.setattr(AuditLogger, "log_event", staticmethod(lambda *a, **k: None))

        rolled_back = {"called": False}
        real_rollback = db_session.rollback

        def _spy_rollback():
            rolled_back["called"] = True
            return real_rollback()

        monkeypatch.setattr(db_session, "rollback", _spy_rollback)

        with pytest.raises(HTTPException):
            _run_export(db_session)

        assert rolled_back["called"] is True


class TestExportSelfLogHappyPath:
    def test_export_persists_exactly_one_self_log_row(self, db_session):
        """Happy path: 200 + exactly one data.bulk.export row with the
        declared purpose and raw_pii_released flag (#2522)."""
        response = _run_export(db_session)

        # 200-equivalent: the function returned a response dict.
        assert "export" in response
        assert response["export"]["record_count"] == 0  # no pre-existing rows

        rows = (
            db_session.query(AuditLogModel)
            .filter(
                AuditLogModel.tenant_id == TENANT,
                AuditLogModel.event_type == "data.bulk.export",
            )
            .all()
        )
        assert len(rows) == 1
        meta = rows[0].metadata_
        assert meta["purpose"] == "compliance_investigation"
        # include_pii=False + masked path -> raw PII not released.
        assert meta["raw_pii_released"] is False
