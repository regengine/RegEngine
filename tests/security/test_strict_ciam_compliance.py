"""Deterministic privileged-auth release contracts.

This module replaces the retired live-HTTP CIAM suite.  The old tests used
Bearer JWTs and a shared administrative header against ``localhost:8400``;
the weekly security job did not start that service, so every assertion could
pass by skipping.  These tests exercise the current dependency boundary
directly: opaque browser sessions for humans, WebAuthn/SSO step-up for
high-risk actions, and a single-purpose database API key for workload tenant
provisioning.

These are source-level authentication contracts.  They do not claim that a
deployed two-tenant matrix, Redis replica behavior, or database RLS posture has
been validated.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest
from fastapi import HTTPException
from shared.api_key_store import APIKeyResponse, DatabaseAPIKeyStore, RateLimitInfo
from starlette.requests import Request

from services.admin.app import privileged_auth as auth
from services.admin.app.auth.session_auth import ActiveSessionContext

TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"


def _run(coro):
    return asyncio.run(coro)


def _request(
    path: str = "/v1/admin/tenants",
    *,
    headers: dict[str, str] | None = None,
) -> Request:
    raw_headers = [(name.lower().encode(), value.encode()) for name, value in (headers or {}).items()]
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": raw_headers,
            "client": ("203.0.113.50", 12345),
            "server": ("testserver", 443),
            "scheme": "https",
            "query_string": b"",
            "http_version": "1.1",
            "root_path": "",
            "state": {},
            "app": SimpleNamespace(state=SimpleNamespace()),
        }
    )


class _Throttle:
    """Deterministic stand-in for the separately tested Redis throttle."""

    def __init__(self) -> None:
        self.failures = 0
        self.resets = 0

    async def is_limited(self, _subject: str) -> bool:
        return False

    async def record_failure(self, _subject: str) -> int:
        self.failures += 1
        return self.failures

    async def reset(self, _subject: str) -> None:
        self.resets += 1


def _session_context(*, sysadmin: bool, auth_method: str) -> ActiveSessionContext:
    return ActiveSessionContext(
        user=SimpleNamespace(
            id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            email="staff@example.test",
            is_sysadmin=sysadmin,
        ),
        session=SimpleNamespace(
            id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            auth_method=auth_method,
            active_membership_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
        ),
    )


def _require_sysadmin(request: Request, throttle: _Throttle):
    return _run(
        auth.require_sysadmin_high_assurance(
            request=request,
            db=MagicMock(),
            crypto_service=MagicMock(),
            throttle=throttle,
        )
    )


def test_bearer_token_cannot_replace_missing_opaque_session():
    throttle = _Throttle()
    request = _request(headers={"Authorization": "Bearer attacker-controlled-token"})
    missing_session = HTTPException(status_code=401, detail="Authentication required.")

    with patch.object(auth, "get_current_active_session_context", side_effect=missing_session):
        with pytest.raises(HTTPException) as exc_info:
            _require_sysadmin(request, throttle)

    assert exc_info.value.status_code == 401
    assert throttle.failures == 1


def test_retired_admin_header_is_rejected_before_session_lookup():
    throttle = _Throttle()
    request = _request(headers={"X-Admin-Key": "retired-shared-credential"})

    with patch.object(
        auth,
        "get_current_active_session_context",
        return_value=_session_context(sysadmin=True, auth_method="webauthn"),
    ) as session_lookup:
        with pytest.raises(HTTPException) as exc_info:
            _require_sysadmin(request, throttle)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "X-Admin-Key is not an accepted authentication method."
    assert throttle.failures == 1
    session_lookup.assert_not_called()


def test_non_sysadmin_high_assurance_session_is_denied():
    throttle = _Throttle()
    with patch.object(
        auth,
        "get_current_active_session_context",
        return_value=_session_context(sysadmin=False, auth_method="webauthn"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            _require_sysadmin(_request(), throttle)

    assert exc_info.value.status_code == 403
    assert throttle.failures == 1


def test_email_code_sysadmin_session_requires_step_up():
    throttle = _Throttle()
    with patch.object(
        auth,
        "get_current_active_session_context",
        return_value=_session_context(sysadmin=True, auth_method="email_otp"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            _require_sysadmin(_request(), throttle)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "requires_step_up"
    assert throttle.failures == 1


@pytest.mark.parametrize("auth_method", ["webauthn", "sso"])
def test_high_assurance_sysadmin_session_is_accepted(auth_method):
    throttle = _Throttle()
    with patch.object(
        auth,
        "get_current_active_session_context",
        return_value=_session_context(sysadmin=True, auth_method=auth_method),
    ):
        actor = _require_sysadmin(_request(), throttle)

    assert actor.actor_type == "staff_user"
    assert actor.auth_method == auth_method
    assert actor.session_id == "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    assert throttle.resets == 1


class _ScalarResult:
    def __init__(self, value) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value


def _review_db(*permissions: str) -> MagicMock:
    db = MagicMock()
    membership = SimpleNamespace(organization_id=TENANT_A)
    role = SimpleNamespace(permissions=list(permissions))
    db.execute.side_effect = [_ScalarResult(membership), _ScalarResult(role)]
    return db


def test_review_read_requires_permission_but_not_step_up():
    throttle = _Throttle()
    db = _review_db("review.read")
    with (
        patch.object(
            auth,
            "get_current_active_session_context",
            return_value=_session_context(sysadmin=False, auth_method="email_otp"),
        ),
        patch.object(auth, "arm_global_admin_context") as arm_context,
        patch.object(auth, "disarm_global_admin_context") as disarm_context,
        patch.object(auth, "bind_authenticated_user_context") as bind_user_context,
    ):
        actor = _run(
            auth.require_review_read(
                request=_request(path="/v1/admin/review/flagged-extractions"),
                db=db,
                crypto_service=MagicMock(),
                throttle=throttle,
            )
        )

    assert actor.tenant_id == TENANT_A
    assert actor.permissions == ("review.read",)
    assert throttle.resets == 1
    assert arm_context.call_args_list == [call(db), call(db)]
    assert disarm_context.call_args_list == [call(db), call(db)]
    bind_user_context.assert_called_once_with(db, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def test_review_decision_requires_high_assurance_before_permission_lookup():
    throttle = _Throttle()
    db = _review_db("review.decide")
    with (
        patch.object(
            auth,
            "get_current_active_session_context",
            return_value=_session_context(sysadmin=False, auth_method="email_otp"),
        ),
        patch.object(auth, "arm_global_admin_context") as arm_context,
        patch.object(auth, "disarm_global_admin_context") as disarm_context,
        patch.object(auth, "bind_authenticated_user_context") as bind_user_context,
    ):
        with pytest.raises(HTTPException) as exc_info:
            _run(
                auth.require_review_decide(
                    request=_request(path="/v1/admin/review/item/approve"),
                    db=db,
                    crypto_service=MagicMock(),
                    throttle=throttle,
                )
            )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "requires_step_up"
    db.execute.assert_not_called()
    arm_context.assert_called_once_with(db)
    disarm_context.assert_called_once_with(db)
    bind_user_context.assert_called_once_with(db, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def test_review_identity_and_tenant_come_from_session_membership():
    throttle = _Throttle()
    db = _review_db("review.decide")
    request = _request(
        path="/v1/admin/review/item/approve",
        headers={"X-Tenant-ID": TENANT_B},
    )
    with (
        patch.object(
            auth,
            "get_current_active_session_context",
            return_value=_session_context(sysadmin=False, auth_method="webauthn"),
        ),
        patch.object(auth, "arm_global_admin_context") as arm_context,
        patch.object(auth, "disarm_global_admin_context") as disarm_context,
        patch.object(auth, "bind_authenticated_user_context") as bind_user_context,
    ):
        actor = _run(
            auth.require_review_decide(
                request=request,
                db=db,
                crypto_service=MagicMock(),
                throttle=throttle,
            )
        )

    assert actor.actor_id == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert actor.tenant_id == TENANT_A
    assert actor.tenant_id != request.headers["X-Tenant-ID"]
    assert arm_context.call_args_list == [call(db), call(db)]
    assert disarm_context.call_args_list == [call(db), call(db)]
    bind_user_context.assert_called_once_with(db, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


class _FakeDatabaseStore(DatabaseAPIKeyStore):
    def __init__(self, api_key: APIKeyResponse | None, *, allowed: bool = True) -> None:
        self.api_key = api_key
        self.allowed = allowed
        self._redis = object()

    async def validate_key(self, _raw_key: str) -> APIKeyResponse | None:
        return self.api_key

    async def check_rate_limit(self, key_id: str, limit: int, window_seconds: int = 60) -> RateLimitInfo:
        assert self.api_key is not None
        assert key_id == self.api_key.key_id
        assert limit == self.api_key.rate_limit_per_minute
        assert window_seconds == 60
        return RateLimitInfo(
            allowed=self.allowed,
            limit=limit,
            remaining=max(0, limit - 1) if self.allowed else 0,
            reset_at=datetime.now(timezone.utc) + timedelta(seconds=window_seconds),
            retry_after=None if self.allowed else window_seconds,
        )


def _workload_key(**overrides) -> APIKeyResponse:
    now = datetime.now(timezone.utc)
    values = {
        "key_id": "rge_live_workload",
        "key_prefix": "rge_live_wor",
        "name": "stripe-tenant-provisioner",
        "tenant_id": None,
        "scopes": [auth.TENANT_PROVISIONER_SCOPE],
        "rate_limit_per_minute": 10,
        "created_at": now,
        "expires_at": now + timedelta(days=30),
    }
    values.update(overrides)
    return APIKeyResponse(**values)


def _require_workload(monkeypatch, api_key: APIKeyResponse | None, *, allowed: bool = True):
    store = _FakeDatabaseStore(api_key, allowed=allowed)
    monkeypatch.setattr(auth, "get_key_store", lambda: store)
    throttle = _Throttle()
    actor = _run(
        auth.require_tenant_provisioner_key(
            request=_request(path="/v1/internal/tenants"),
            x_regengine_api_key="rge_live_workload.raw-secret",  # pragma: allowlist secret
            throttle=throttle,
        )
    )
    return actor, throttle


def test_exact_tenantless_workload_key_is_accepted(monkeypatch):
    actor, throttle = _require_workload(monkeypatch, _workload_key())

    assert actor.actor_type == "workload_api_key"
    assert actor.actor_id == "rge_live_workload"
    assert actor.actor_name == "stripe-tenant-provisioner"
    assert actor.auth_method == "database_api_key"
    assert throttle.resets == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"tenant_id": TENANT_A},
        {"scopes": ["internal.tenants.create", "review.read"]},
        {"scopes": ["tenants.create"]},
        {"expires_at": None},
        {"rate_limit_per_minute": 11},
    ],
)
def test_wrong_class_or_scope_workload_key_is_denied(monkeypatch, overrides):
    store = _FakeDatabaseStore(_workload_key(**overrides))
    monkeypatch.setattr(auth, "get_key_store", lambda: store)

    with pytest.raises(HTTPException) as exc_info:
        _run(
            auth.require_tenant_provisioner_key(
                request=_request(path="/v1/internal/tenants"),
                x_regengine_api_key="rge_live_workload.raw-secret",  # pragma: allowlist secret
                throttle=_Throttle(),
            )
        )

    assert exc_info.value.status_code == 403


def test_expired_or_revoked_workload_key_is_denied(monkeypatch):
    store = _FakeDatabaseStore(None)
    monkeypatch.setattr(auth, "get_key_store", lambda: store)

    with pytest.raises(HTTPException) as exc_info:
        _run(
            auth.require_tenant_provisioner_key(
                request=_request(path="/v1/internal/tenants"),
                x_regengine_api_key="rge_revoked.raw-secret",  # pragma: allowlist secret
                throttle=_Throttle(),
            )
        )

    assert exc_info.value.status_code == 401


def test_workload_rate_limit_is_enforced(monkeypatch):
    store = _FakeDatabaseStore(_workload_key(), allowed=False)
    monkeypatch.setattr(auth, "get_key_store", lambda: store)

    with pytest.raises(HTTPException) as exc_info:
        _run(
            auth.require_tenant_provisioner_key(
                request=_request(path="/v1/internal/tenants"),
                x_regengine_api_key="rge_live_workload.raw-secret",  # pragma: allowlist secret
                throttle=_Throttle(),
            )
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers["Retry-After"] == "60"
