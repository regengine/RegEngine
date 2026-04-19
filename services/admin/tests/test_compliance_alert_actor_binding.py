"""Regression tests for #1384 — compliance alert acknowledge/resolve take
the actor ID from the authenticated user, never from the request body.

Attack the bug directly: if ``AlertActionRequest`` ever regains a ``user_id``
field, or if the route handlers forward a client-supplied value into the
service layer, these tests fail.
"""

from __future__ import annotations

import inspect
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import Depends, HTTPException


# ---------------------------------------------------------------------------
# Schema-level regression
# ---------------------------------------------------------------------------


def test_alert_action_request_has_no_user_id_field():
    """The client MUST NOT be able to pass ``user_id`` in the request body."""
    from services.admin.app.compliance_routes import AlertActionRequest

    fields = AlertActionRequest.model_fields  # pydantic v2
    assert "user_id" not in fields, (
        "AlertActionRequest.user_id is a well-known actor-spoofing surface "
        "(#1384). The actor must come from Depends(get_current_user)."
    )
    # Only 'notes' is acceptable.
    assert set(fields.keys()) == {"notes"}


def test_alert_action_request_rejects_client_supplied_user_id_silently():
    """Extra fields like ``user_id`` must not populate anything on the model."""
    from services.admin.app.compliance_routes import AlertActionRequest

    req = AlertActionRequest.model_validate({
        "user_id": "11111111-1111-1111-1111-111111111111",  # attacker payload
        "notes": "looks legit",
    })
    assert req.notes == "looks legit"
    # No user_id attribute should exist.
    assert not hasattr(req, "user_id") or getattr(req, "user_id", None) is None


# ---------------------------------------------------------------------------
# Handler-level regression — the handler must use current_user.id
# ---------------------------------------------------------------------------


def test_acknowledge_alert_handler_depends_on_get_current_user():
    from services.admin.app.compliance_routes import acknowledge_alert
    from services.admin.app.dependencies import get_current_user

    sig = inspect.signature(acknowledge_alert)
    current_user_param = sig.parameters.get("current_user")
    assert current_user_param is not None, (
        "acknowledge_alert must declare current_user: UserModel = "
        "Depends(get_current_user)"
    )

    # The default is a FastAPI Depends marker — peel it open.
    default = current_user_param.default
    assert hasattr(default, "dependency"), (
        "current_user must be wired via FastAPI Depends()"
    )
    assert default.dependency is get_current_user


def test_resolve_alert_handler_depends_on_get_current_user():
    from services.admin.app.compliance_routes import resolve_alert
    from services.admin.app.dependencies import get_current_user

    sig = inspect.signature(resolve_alert)
    current_user_param = sig.parameters.get("current_user")
    assert current_user_param is not None
    default = current_user_param.default
    assert hasattr(default, "dependency")
    assert default.dependency is get_current_user


# ---------------------------------------------------------------------------
# Behavioral regression — call the handlers as plain functions and confirm
# the value that reaches the service layer is the authenticated user's id.
# ---------------------------------------------------------------------------


class _FakeUser:
    def __init__(self, user_id):
        self.id = user_id


class _FakeAlert:
    """Minimal stand-in for ComplianceAlertModel."""

    def __init__(self, tenant_id):
        self.id = uuid.uuid4()
        self.tenant_id = tenant_id
        self.source_type = "MANUAL"
        self.source_id = "test-source"
        self.title = "t"
        self.summary = None
        self.severity = "HIGH"
        self.countdown_start = datetime.now(timezone.utc)
        self.countdown_end = datetime.now(timezone.utc) + timedelta(hours=24)
        self.countdown_hours = 24
        self.required_actions = []
        self.status = "ACKNOWLEDGED"
        self.acknowledged_at = None
        self.acknowledged_by = None
        self.resolved_at = None
        self.resolved_by = None
        self.match_reason = None
        self.created_at = datetime.now(timezone.utc)
        self.resolution_notes = None

    def to_dict(self):
        return {
            "id": str(self.id),
            "tenant_id": str(self.tenant_id),
            "source_type": self.source_type,
            "source_id": self.source_id,
            "title": self.title,
            "summary": self.summary,
            "severity": self.severity,
            "severity_emoji": "!",
            "countdown_start": self.countdown_start.isoformat(),
            "countdown_end": self.countdown_end.isoformat(),
            "countdown_hours": self.countdown_hours,
            "countdown_seconds": 0,
            "countdown_display": "0h",
            "is_expired": False,
            "required_actions": [],
            "status": self.status,
            "acknowledged_at": None,
            "acknowledged_by": self.acknowledged_by,
            "resolved_at": None,
            "resolved_by": self.resolved_by,
            "match_reason": None,
            "created_at": self.created_at.isoformat(),
        }


def test_acknowledge_alert_stamps_authenticated_user_not_request_user(monkeypatch):
    """End-to-end: handler -> service stamps acknowledged_by = current_user.id."""
    from services.admin.app import compliance_routes
    from services.admin.app.compliance_routes import (
        AlertActionRequest,
        acknowledge_alert,
    )

    authed_user_id = uuid.uuid4()
    current_user = _FakeUser(authed_user_id)
    tenant_id = uuid.uuid4()
    alert_id = uuid.uuid4()

    captured = {}

    class FakeService:
        def __init__(self, session):
            pass

        # #1405: signature now includes tenant_id for defense-in-depth.
        def acknowledge_alert(self, aid, tid, actor_id):
            captured["actor_id"] = actor_id
            captured["alert_id"] = aid
            captured["tenant_id"] = tid
            alert = _FakeAlert(tenant_id)
            alert.acknowledged_by = actor_id
            return alert

    monkeypatch.setattr(compliance_routes, "ComplianceServiceSync", FakeService)

    req = AlertActionRequest(notes="routine")
    # Call handler directly; this is what the router would invoke.
    response = acknowledge_alert(
        tenant_id=str(tenant_id),
        alert_id=str(alert_id),
        request=req,
        current_user=current_user,
        session=MagicMock(),
    )

    # The UUID passed to the service MUST be the authenticated user's id,
    # stringified. Any attempt to read a value off the request body would
    # diverge.
    assert captured["actor_id"] == str(authed_user_id)
    assert response.acknowledged_by == str(authed_user_id)


def test_resolve_alert_stamps_authenticated_user_not_request_user(monkeypatch):
    from services.admin.app import compliance_routes
    from services.admin.app.compliance_routes import (
        AlertActionRequest,
        resolve_alert,
    )

    authed_user_id = uuid.uuid4()
    current_user = _FakeUser(authed_user_id)
    tenant_id = uuid.uuid4()
    alert_id = uuid.uuid4()

    captured = {}

    class FakeService:
        def __init__(self, session):
            pass

        # #1405: signature now includes tenant_id for defense-in-depth.
        def resolve_alert(self, aid, tid, actor_id, notes):
            captured["actor_id"] = actor_id
            captured["notes"] = notes
            captured["tenant_id"] = tid
            alert = _FakeAlert(tenant_id)
            alert.status = "RESOLVED"
            alert.resolved_by = actor_id
            alert.resolution_notes = notes
            return alert

    monkeypatch.setattr(compliance_routes, "ComplianceServiceSync", FakeService)

    req = AlertActionRequest(notes="fixed it")
    response = resolve_alert(
        tenant_id=str(tenant_id),
        alert_id=str(alert_id),
        request=req,
        current_user=current_user,
        session=MagicMock(),
    )

    assert captured["actor_id"] == str(authed_user_id)
    assert captured["notes"] == "fixed it"
    assert response.resolved_by == str(authed_user_id)


def test_service_layer_still_stamps_acknowledged_by_from_caller_arg():
    """Defense in depth: even the service layer should honor the actor arg,
    not pull from anywhere else. This catches a regression where the route
    starts computing the actor but the service stops using it."""
    from services.admin.app.compliance_service_sync import ComplianceServiceSync
    from services.admin.app.compliance_models import ComplianceAlertModel

    # Spy session that records mutations.
    captured = {}

    class FakeResult:
        def scalar_one_or_none(self_inner):
            return captured.get("alert")

        def fetchall(self_inner):
            return []

        def scalars(self_inner):
            return SimpleNamespace(all=lambda: [])

    class FakeSession:
        def execute(self_inner, stmt, params=None):
            return FakeResult()

        def commit(self_inner):
            pass

        def refresh(self_inner, obj):
            pass

        def add(self_inner, obj):
            captured["added"] = obj

    alert_tenant = uuid.uuid4()
    alert = ComplianceAlertModel(
        tenant_id=alert_tenant,
        source_type="MANUAL",
        source_id="x",
        title="x",
        severity="HIGH",
        countdown_start=datetime.now(timezone.utc),
        countdown_end=datetime.now(timezone.utc) + timedelta(hours=24),
        countdown_hours=24,
        required_actions=[],
        status="ACTIVE",
    )
    captured["alert"] = alert

    service = ComplianceServiceSync(FakeSession())
    actor_id = str(uuid.uuid4())
    # #1405: service signature requires (alert_id, tenant_id, actor_id).
    out = service.acknowledge_alert(uuid.uuid4(), alert_tenant, actor_id)

    assert out is alert
    assert alert.acknowledged_by == actor_id
