"""Adversarial checks for the admin audit export and chain verifier.

These pin three breaks found by exercising the local audit path:

* A production process can mask emails with an ephemeral salt when the
  production signal is not exactly ``REGENGINE_ENV=production``.
* ``include_verification`` hashed the redacted export view, so a clean
  chain looked broken and a tampered actor email was not a distinct result.
* ``verify_chain`` raised on null or non-object blocks, and a deleted
  chain prefix still verified because the first row's parent was never loaded.
* Spreadsheet formula text in exported fields was returned unchanged.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

service_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("sqlalchemy")

from app import audit_routes  # noqa: E402
from app.audit import AuditLogger, compute_integrity_hash  # noqa: E402
from app.audit_integrity import verify_chain  # noqa: E402
from app.audit_middleware import AuditContextMiddleware  # noqa: E402
from app.sqlalchemy_models import AuditLogModel  # noqa: E402

TENANT = UUID("00000000-0000-0000-0000-000000000099")
USER_ID = UUID("00000000-0000-0000-0000-000000000001")

_SALT_ENV_NAMES = (
    "AUDIT_PII_HASH_SALT",
    "REGENGINE_ENV",
    "ENV",
    "ENVIRONMENT",
    "RAILWAY_ENVIRONMENT",
    "RAILWAY_ENVIRONMENT_NAME",
    "VERCEL_ENV",
)


def _clear_salt_env(monkeypatch) -> None:
    for name in _SALT_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def _stub_user():
    return SimpleNamespace(id=USER_ID, email="auditor@example.com", is_sysadmin=True)


def _run_export(db, **overrides):
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
        include_verification=True,
        include_pii=False,
    )
    kwargs.update(overrides)
    return audit_routes.export_audit_logs(**kwargs)


def _log(db, **overrides):
    payload = dict(
        db=db,
        tenant_id=TENANT,
        event_type="auth.login",
        action="login",
        event_category="auth",
        severity="warning",
        actor_id=USER_ID,
        actor_email="jane@example.com",
        actor_ip="203.0.113.9",
        actor_ua="pytest-ua",
        resource_type="user",
        resource_id="user-1",
        endpoint="POST /login",
        metadata={"note": "desk"},
    )
    payload.update(overrides)
    entry_id = AuditLogger.log_event(**payload)
    db.flush()
    return entry_id


# ---------------------------------------------------------------------------
# Missing salt must fail closed for every production signal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "env_name",
    [
        "REGENGINE_ENV",
        "ENV",
        "ENVIRONMENT",
        "RAILWAY_ENVIRONMENT",
        "RAILWAY_ENVIRONMENT_NAME",
        "VERCEL_ENV",
    ],
)
def test_missing_salt_fails_closed_for_each_production_signal(monkeypatch, env_name):
    _clear_salt_env(monkeypatch)
    monkeypatch.setenv(env_name, " production ")
    with pytest.raises(RuntimeError, match="AUDIT_PII_HASH_SALT"):
        audit_routes._pii_hash_salt()


def test_short_salt_fails_closed_in_production(monkeypatch):
    _clear_salt_env(monkeypatch)
    monkeypatch.setenv("REGENGINE_ENV", "production")
    monkeypatch.setenv("AUDIT_PII_HASH_SALT", "short")
    with pytest.raises(RuntimeError, match="AUDIT_PII_HASH_SALT"):
        audit_routes._mask_email("jane@example.com")


def test_development_still_masks_without_a_configured_salt(monkeypatch):
    _clear_salt_env(monkeypatch)
    monkeypatch.setenv("REGENGINE_ENV", "development")
    masked = audit_routes._mask_email("jane@example.com")
    assert masked.startswith("masked:")
    assert "jane@example.com" not in masked


# ---------------------------------------------------------------------------
# Verifier fail-closed on malformed payloads, and verified stays non-negative
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "entry",
    [
        {"id": 1, "event": None, "resource": {"id": None}, "integrity": {"hash": "ab"}, "metadata": {}},
        {"id": 2, "event": {"type": "a", "action": "b"}, "resource": None, "integrity": {"hash": "ab"}},
        {"id": 3, "event": {"type": "a", "action": "b"}, "resource": {}, "integrity": None},
        {"id": 4, "event": "login", "integrity": {"hash": "ab"}},
        "not-a-dict",
    ],
)
def test_verify_chain_malformed_entry_is_invalid_without_raising(entry):
    result = verify_chain([entry])
    assert result["valid"] is False
    assert result["errors"]
    assert result["verified"] >= 0
    assert result["verified"] <= result["total_entries"]


def test_verified_count_does_not_go_negative_when_one_row_has_many_errors():
    """One tampered row can fail the link, the sequence, and the hash."""
    timestamp = "2026-04-20T00:00:00+00:00"
    first_hash = compute_integrity_hash(
        prev_hash=None,
        tenant_id="t-1",
        timestamp=timestamp,
        event_type="auth.login",
        action="login",
        resource_id=None,
        metadata={},
        actor_id="a-1",
        actor_email="a@example.com",
        severity="info",
        endpoint="/login",
        sequence_num=1,
    )
    first = {
        "id": 1,
        "tenant_id": "t-1",
        "timestamp": timestamp,
        "event": {"type": "auth.login", "action": "login"},
        "resource": {"id": None},
        "metadata": {},
        "actor": {"id": "a-1", "email": "a@example.com"},
        "severity": "info",
        "endpoint": "/login",
        "integrity": {"prev_hash": None, "hash": first_hash, "sequence_num": 1},
    }
    second = {
        "id": 2,
        "tenant_id": "t-1",
        "timestamp": "2026-04-20T00:00:01+00:00",
        "event": {"type": "auth.login", "action": "login"},
        "resource": {"id": None},
        "metadata": {},
        "actor": {"id": "a-1", "email": "a@example.com"},
        "severity": "info",
        "endpoint": "/login",
        "integrity": {"prev_hash": "b" * 64, "hash": "c" * 64, "sequence_num": 4},
    }
    result = verify_chain([first, second])
    assert result["valid"] is False
    assert len(result["errors"]) >= 2
    assert result["verified"] == 1


# ---------------------------------------------------------------------------
# Export verification uses stored fields, and formula text is neutralized
# ---------------------------------------------------------------------------


def test_clean_export_verifies_and_tampered_actor_does_not(db_session, monkeypatch):
    monkeypatch.setenv("AUDIT_PII_HASH_SALT", "unit-test-salt-value")
    monkeypatch.setenv("REGENGINE_ENV", "test")
    entry_id = _log(db_session, metadata={"note": "call jane@example.com before shipping"})

    clean = _run_export(db_session)
    verification = clean["integrity"]["chain_verification"]
    assert verification["valid"] is True, verification
    published = json.dumps(clean["entries"])
    assert "jane@example.com" not in published

    row = db_session.get(AuditLogModel, entry_id)
    row.actor_email = "attacker@example.com"
    db_session.commit()

    tampered = _run_export(db_session, purpose="security_incident")
    tampered_verification = tampered["integrity"]["chain_verification"]
    assert tampered_verification["valid"] is False
    assert any(
        err["error"] == "integrity_hash_mismatch" and err["id"] == entry_id for err in tampered_verification["errors"]
    )


def test_time_window_keeps_the_parent_link(db_session, monkeypatch):
    """A later slice is valid when the earlier row is still stored."""
    monkeypatch.setenv("AUDIT_PII_HASH_SALT", "unit-test-salt-value")
    monkeypatch.setenv("REGENGINE_ENV", "test")
    _log(db_session, action="one")
    _log(db_session, action="two")
    _log(db_session, action="three")
    db_session.commit()
    stored = (
        db_session.query(AuditLogModel)
        .filter(AuditLogModel.tenant_id == TENANT)
        .order_by(AuditLogModel.sequence_num.asc())
        .all()
    )
    start = stored[1].timestamp.isoformat()

    exported = _run_export(db_session, start=start)
    actions = [entry["event"]["action"] for entry in exported["entries"]]
    assert "one" not in actions
    assert "two" in actions
    verification = exported["integrity"]["chain_verification"]
    assert verification["valid"] is True, verification


def test_deleted_chain_prefix_does_not_verify(db_session, monkeypatch):
    monkeypatch.setenv("AUDIT_PII_HASH_SALT", "unit-test-salt-value")
    monkeypatch.setenv("REGENGINE_ENV", "test")
    first_id = _log(db_session, action="one")
    _log(db_session, action="two")
    _log(db_session, action="three")
    db_session.query(AuditLogModel).filter(AuditLogModel.id == first_id).delete()
    db_session.commit()

    exported = _run_export(db_session)
    verification = exported["integrity"]["chain_verification"]
    assert verification["valid"] is False, verification
    assert any(err["error"] == "chain_anchor_missing" for err in verification["errors"])


def test_export_neutralizes_spreadsheet_formulas(db_session, monkeypatch):
    monkeypatch.setenv("AUDIT_PII_HASH_SALT", "unit-test-salt-value")
    monkeypatch.setenv("REGENGINE_ENV", "test")
    formula = "=cmd|'/c calc'!A0"
    _log(
        db_session,
        action=formula,
        endpoint="+1-415-555-0100",
        metadata={"formula": formula, "safe": "role-change"},
    )

    exported = _run_export(db_session)
    login = next(entry for entry in exported["entries"] if entry["event"]["type"] == "auth.login")
    assert login["event"]["action"] == "'" + formula
    assert login["endpoint"] == "'+1-415-555-0100"
    assert login["metadata"]["formula"] == "'" + formula
    assert login["metadata"]["safe"] == "role-change"
    assert exported["integrity"]["chain_verification"]["valid"] is True


# ---------------------------------------------------------------------------
# Audit context must not keep hostile request ids or control characters
# ---------------------------------------------------------------------------


def _request(*, request_id: str, user_agent: str):
    from unittest.mock import MagicMock

    req = MagicMock()
    req.url.path = "/v1/audit/export"
    req.method = "GET"
    req.headers = {"user-agent": user_agent}
    req.client = MagicMock()
    req.client.host = "203.0.113.8"
    req.state = type("_State", (), {})()
    req.state.request_id = request_id
    return req


@pytest.mark.asyncio
async def test_audit_context_rejects_hostile_request_id_and_user_agent():
    middleware = AuditContextMiddleware(app=None)
    hostile_id = "legit\r\nX-Admin: true"
    request = _request(request_id=hostile_id, user_agent="Mozilla/5.0\r\nX-Injected: 1" + ("A" * 800))

    async def _call_next(req):
        return None

    await middleware.dispatch(request, _call_next)
    context = request.state.audit_context
    assert context["request_id"] != hostile_id
    assert "\r" not in context["request_id"]
    assert "\n" not in context["request_id"]
    assert len(context["request_id"]) <= 128
    assert "\r" not in context["actor_ua"]
    assert "\n" not in context["actor_ua"]
    assert len(context["actor_ua"]) <= 512
