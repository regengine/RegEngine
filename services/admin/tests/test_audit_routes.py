"""Focused coverage for ``app/audit_routes.py`` — the audit export endpoint.

Covers the main public behavior of ``GET /v1/audit/export`` by calling
``export_audit_logs`` directly against the SQLite-backed ``db_session``
fixture (no network, no live services):

* Happy path: signed bundle shape, bundle-hash recomputation, entry
  shape, and the ``data.bulk.export`` self-log row.
* Purpose gate: an invalid ``purpose`` is a 400, not a silent export.
* Tenant gate: missing tenant context is a 403.
* PII masking: masked by default, raw only for entitled callers with
  ``include_pii=true``, and per-user erasure markers force masking even
  for entitled callers.
* Filters: invalid category/severity/date are 400s; category scoping
  and tenant isolation hold.
* Metadata redaction: raw payload emails do not leak through metadata.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException

service_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("sqlalchemy")

from app import audit_routes  # noqa: E402
from app.audit import AuditLogger  # noqa: E402
from app.sqlalchemy_models import AuditLogModel  # noqa: E402

TENANT = UUID("00000000-0000-0000-0000-000000000099")
TENANT_OTHER = UUID("00000000-0000-0000-0000-0000000000aa")
USER_ID = UUID("00000000-0000-0000-0000-000000000001")
ACTOR_ID = UUID("00000000-0000-0000-0000-000000000002")


def _sysadmin_user():
    return SimpleNamespace(id=USER_ID, email="auditor@example.com", is_sysadmin=True)


def _plain_user():
    return SimpleNamespace(id=USER_ID, email="auditor@example.com", is_sysadmin=False)


def _run_export(db, user=None, tenant=TENANT, **overrides):
    db.info["tenant_id"] = tenant
    kwargs = dict(
        db=db,
        current_user=user if user is not None else _sysadmin_user(),
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


def _seed_row(db, tenant=TENANT, **overrides):
    kwargs = dict(
        tenant_id=tenant,
        event_type="auth.login",
        action="login",
        event_category="auth",
        severity="info",
        actor_id=ACTOR_ID,
        actor_email="jane.doe@example.com",
        actor_ip="10.0.0.1",
        actor_ua="pytest-agent/1.0",
        resource_type="session",
        resource_id="res-1",
        endpoint="/v1/auth/login",
        metadata={"safe": "role-change"},
    )
    kwargs.update(overrides)
    entry_id = AuditLogger.log_event(db=db, **kwargs)
    db.flush()
    return entry_id


class TestExportHappyPath:
    def test_bundle_shape_and_hash(self, db_session):
        _seed_row(db_session)
        response = _run_export(db_session)

        export = response["export"]
        assert export["tenant_id"] == str(TENANT)
        assert export["record_count"] == 1
        assert response["integrity"]["bundle_hash"] == export["bundle_hash"]

        recomputed = hashlib.sha256(
            json.dumps(response["entries"], sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        assert export["bundle_hash"] == recomputed

    def test_entry_shape(self, db_session):
        _seed_row(db_session)
        response = _run_export(db_session)

        entry = response["entries"][0]
        assert entry["tenant_id"] == str(TENANT)
        assert entry["event"] == {
            "type": "auth.login",
            "category": "auth",
            "action": "login",
            "severity": "info",
        }
        assert entry["resource"] == {"type": "session", "id": "res-1"}
        assert entry["integrity"]["hash"]
        assert "sequence_num" in entry["integrity"]

    def test_self_log_row_carries_purpose(self, db_session):
        _seed_row(db_session)
        _run_export(db_session, purpose="security_incident")

        rows = (
            db_session.query(AuditLogModel)
            .filter(
                AuditLogModel.tenant_id == TENANT,
                AuditLogModel.event_type == "data.bulk.export",
            )
            .all()
        )
        assert len(rows) == 1
        assert rows[0].metadata_["purpose"] == "security_incident"

    def test_verification_flag_adds_chain_report(self, db_session):
        _seed_row(db_session)
        plain = _run_export(db_session)
        assert "chain_verification" not in plain["integrity"]

        verified = _run_export(db_session, include_verification=True)
        report = verified["integrity"]["chain_verification"]
        assert isinstance(report, dict)
        assert "valid" in report


class TestExportGates:
    def test_invalid_purpose_is_400(self, db_session):
        with pytest.raises(HTTPException) as exc_info:
            _run_export(db_session, purpose="exfiltrate_all_the_things")
        assert exc_info.value.status_code == 400

    def test_missing_tenant_context_is_403(self, db_session):
        db_session.info.pop("tenant_id", None)
        with pytest.raises(HTTPException) as exc_info:
            audit_routes.export_audit_logs(
                db=db_session,
                current_user=_sysadmin_user(),
                purpose="compliance_investigation",
                start=None,
                end=None,
                event_category=None,
                severity=None,
                limit=10000,
                include_verification=False,
                include_pii=False,
            )
        assert exc_info.value.status_code == 403

    def test_invalid_date_format_is_400(self, db_session):
        with pytest.raises(HTTPException) as exc_info:
            _run_export(db_session, start="not-a-date")
        assert exc_info.value.status_code == 400

    def test_invalid_event_category_is_400(self, db_session):
        with pytest.raises(HTTPException) as exc_info:
            _run_export(db_session, event_category="nope")
        assert exc_info.value.status_code == 400

    def test_invalid_severity_is_400(self, db_session):
        with pytest.raises(HTTPException) as exc_info:
            _run_export(db_session, severity="nope")
        assert exc_info.value.status_code == 400


class TestExportPiiMasking:
    def test_pii_masked_by_default(self, db_session):
        _seed_row(db_session)
        response = _run_export(db_session)

        actor = response["entries"][0]["actor"]
        assert actor["pii_masked"] is True
        assert actor["email"].startswith("masked:")
        assert "jane.doe@example.com" not in json.dumps(response["entries"])
        assert actor["ip"] is None
        assert actor["user_agent"] is None

    def test_sysadmin_with_include_pii_gets_raw_values(self, db_session):
        _seed_row(db_session)
        response = _run_export(db_session, include_pii=True)

        actor = response["entries"][0]["actor"]
        assert actor["pii_masked"] is False
        assert actor["email"] == "jane.doe@example.com"
        assert actor["ip"] == "10.0.0.1"
        assert actor["user_agent"] == "pytest-agent/1.0"

    def test_unentitled_caller_stays_masked_even_when_requested(self, db_session):
        _seed_row(db_session)
        response = _run_export(db_session, user=_plain_user(), include_pii=True)

        actor = response["entries"][0]["actor"]
        assert actor["pii_masked"] is True
        assert actor["email"].startswith("masked:")

    def test_erasure_marker_forces_masking_for_entitled_caller(self, db_session):
        _seed_row(
            db_session,
            event_type="data.write",
            action="update",
            event_category="data",
        )
        AuditLogger.log_event(
            db=db_session,
            tenant_id=TENANT,
            event_type="data.erasure",
            action="gdpr_anonymize_user",
            event_category="data",
            resource_id=str(ACTOR_ID),
            metadata={
                "details": {
                    "marker_kind": "per_user_anonymization_order",
                    "redacted_user_id": str(ACTOR_ID),
                    "redacted_tenant_id": str(TENANT),
                }
            },
        )
        db_session.flush()

        response = _run_export(db_session, include_pii=True)
        historical = next(entry for entry in response["entries"] if entry["event"]["type"] == "data.write")
        assert historical["actor"]["pii_masked"] is True
        assert historical["actor"]["email"].startswith("masked:")


class TestExportFilters:
    def test_category_filter_scopes_results(self, db_session):
        _seed_row(db_session, event_category="auth", event_type="auth.login")
        _seed_row(
            db_session,
            event_category="data",
            event_type="data.write",
            resource_id="res-2",
        )
        response = _run_export(db_session, event_category="auth")

        assert response["export"]["record_count"] == 1
        assert response["entries"][0]["event"]["category"] == "auth"

    def test_severity_filter_keeps_minimum_and_above(self, db_session):
        _seed_row(db_session, severity="critical", resource_id="res-crit")
        _seed_row(db_session, severity="info", resource_id="res-info")
        response = _run_export(db_session, severity="error")

        resource_ids = {entry["resource"]["id"] for entry in response["entries"]}
        assert "res-crit" in resource_ids
        assert "res-info" not in resource_ids

    def test_future_time_range_returns_empty_bundle(self, db_session):
        _seed_row(db_session)
        start = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        response = _run_export(db_session, start=start)

        assert response["export"]["record_count"] == 0
        assert response["entries"] == []
        assert response["integrity"]["chain_start"] is None

    def test_other_tenant_rows_are_excluded(self, db_session):
        _seed_row(db_session, tenant=TENANT)
        _seed_row(db_session, tenant=TENANT_OTHER, resource_id="other-res")
        response = _run_export(db_session, tenant=TENANT)

        assert response["export"]["record_count"] == 1
        assert response["entries"][0]["tenant_id"] == str(TENANT)

    def test_metadata_pii_is_redacted_on_export(self, db_session):
        _seed_row(db_session, metadata={"email": "invitee@example.com", "safe": "ok"})
        response = _run_export(db_session)

        payload = json.dumps(response["entries"])
        assert "invitee@example.com" not in payload
        assert response["entries"][0]["metadata"]["safe"] == "ok"
