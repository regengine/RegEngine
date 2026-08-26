"""Security regression tests for human and workload privileged auth."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from shared.api_key_store import APIKeyResponse, DatabaseAPIKeyStore, RateLimitInfo
from starlette.requests import Request

from services.admin.app import privileged_auth as mod
from services.admin.app.auth.session_auth import ActiveSessionContext


def _run(coro):
    return asyncio.run(coro)


def _request(
    path: str = "/v1/admin/keys",
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
    def __init__(self) -> None:
        self.limited = False
        self.failures = 0
        self.resets = 0
        self.failure_subjects: list[str] = []
        self.reset_subjects: list[str] = []

    async def is_limited(self, _subject: str) -> bool:
        return self.limited

    async def record_failure(self, subject: str) -> int:
        self.failures += 1
        self.failure_subjects.append(subject)
        return self.failures

    async def reset(self, subject: str) -> None:
        self.resets += 1
        self.reset_subjects.append(subject)


def _session_context(*, sysadmin: bool, auth_method: str = "webauthn") -> ActiveSessionContext:
    return ActiveSessionContext(
        user=SimpleNamespace(
            id="11111111-1111-1111-1111-111111111111",
            email="staff@example.test",
            is_sysadmin=sysadmin,
        ),
        session=SimpleNamespace(
            id="22222222-2222-2222-2222-222222222222",
            auth_method=auth_method,
            active_membership_id="33333333-3333-3333-3333-333333333333",
        ),
    )


def test_legacy_admin_header_cannot_replace_missing_browser_session():
    throttle = _Throttle()
    request = _request(headers={"X-Admin-Key": "retired-secret"})

    with pytest.raises(HTTPException) as exc_info:
        _run(
            mod.require_sysadmin_high_assurance(
                request=request,
                db=MagicMock(),
                crypto_service=MagicMock(),
                throttle=throttle,
            )
        )

    assert exc_info.value.status_code == 401
    assert throttle.failures == 1


def test_legacy_admin_header_is_rejected_even_with_valid_session():
    throttle = _Throttle()
    with patch.object(
        mod,
        "get_current_active_session_context",
        return_value=_session_context(sysadmin=True, auth_method="webauthn"),
    ) as session_lookup:
        with pytest.raises(HTTPException) as exc_info:
            _run(
                mod.require_sysadmin_high_assurance(
                    request=_request(headers={"X-Admin-Key": "retired-secret"}),
                    db=MagicMock(),
                    crypto_service=MagicMock(),
                    throttle=throttle,
                )
            )

    assert exc_info.value.status_code == 401
    assert throttle.failures == 1
    session_lookup.assert_not_called()


def test_non_sysadmin_high_assurance_session_is_denied():
    throttle = _Throttle()
    with patch.object(mod, "get_current_active_session_context", return_value=_session_context(sysadmin=False)):
        with pytest.raises(HTTPException) as exc_info:
            _run(
                mod.require_sysadmin_high_assurance(
                    request=_request(),
                    db=MagicMock(),
                    crypto_service=MagicMock(),
                    throttle=throttle,
                )
            )

    assert exc_info.value.status_code == 403
    assert throttle.failures == 1


def test_email_code_sysadmin_session_requires_step_up():
    throttle = _Throttle()
    with patch.object(
        mod,
        "get_current_active_session_context",
        return_value=_session_context(sysadmin=True, auth_method="email_otp"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            _run(
                mod.require_sysadmin_high_assurance(
                    request=_request(),
                    db=MagicMock(),
                    crypto_service=MagicMock(),
                    throttle=throttle,
                )
            )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "requires_step_up"


@pytest.mark.parametrize("auth_method", ["webauthn", "sso"])
def test_high_assurance_sysadmin_session_is_accepted(auth_method):
    throttle = _Throttle()
    with patch.object(
        mod,
        "get_current_active_session_context",
        return_value=_session_context(sysadmin=True, auth_method=auth_method),
    ):
        actor = _run(
            mod.require_sysadmin_high_assurance(
                request=_request(),
                db=MagicMock(),
                crypto_service=MagicMock(),
                throttle=throttle,
            )
        )

    assert actor.actor_type == "staff_user"
    assert actor.auth_method == auth_method
    assert actor.session_id == "22222222-2222-2222-2222-222222222222"
    assert throttle.resets == 1


class _FakeDatabaseStore(DatabaseAPIKeyStore):
    def __init__(self, api_key: APIKeyResponse | None, *, allowed: bool = True) -> None:
        self.api_key = api_key
        self.allowed = allowed
        self.validated_raw_key: str | None = None
        # Workload rate limiting is required to be backed by a shared client.
        # This sentinel stands in for that capability in focused unit tests.
        self._redis = object()

    async def validate_key(self, raw_key: str) -> APIKeyResponse | None:
        self.validated_raw_key = raw_key
        return self.api_key

    async def check_rate_limit(self, key_id: str, limit: int, window_seconds: int = 60) -> RateLimitInfo:
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
        "scopes": [mod.TENANT_PROVISIONER_SCOPE],
        "rate_limit_per_minute": 10,
        "created_at": now,
        "expires_at": now + timedelta(days=30),
    }
    values.update(overrides)
    return APIKeyResponse(**values)


def _require_workload(monkeypatch, api_key: APIKeyResponse | None, *, allowed: bool = True):
    store = _FakeDatabaseStore(api_key, allowed=allowed)
    monkeypatch.setattr(mod, "get_key_store", lambda: store)
    throttle = _Throttle()
    request = _request(path="/v1/internal/tenants")
    return (
        _run(
            mod.require_tenant_provisioner_key(
                request=request,
                x_regengine_api_key="rge_live_workload.raw-secret",  # pragma: allowlist secret
                throttle=throttle,
            )
        ),
        store,
        throttle,
    )


def test_exact_tenantless_workload_key_is_accepted(monkeypatch):
    actor, store, throttle = _require_workload(monkeypatch, _workload_key())

    assert actor.actor_type == "workload_api_key"
    assert actor.actor_id == "rge_live_workload"
    assert actor.actor_name == "stripe-tenant-provisioner"
    assert store.validated_raw_key == "rge_live_workload.raw-secret"
    assert throttle.resets == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"tenant_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"},
        {"scopes": ["*"]},
        {"scopes": [mod.TENANT_PROVISIONER_SCOPE, "review.read"]},
        {"expires_at": None},
        {"rate_limit_per_minute": 11},
    ],
)
def test_wrong_workload_key_policy_is_denied(monkeypatch, overrides):
    key = _workload_key(**overrides)
    store = _FakeDatabaseStore(key)
    monkeypatch.setattr(mod, "get_key_store", lambda: store)
    throttle = _Throttle()

    with pytest.raises(HTTPException) as exc_info:
        _run(
            mod.require_tenant_provisioner_key(
                request=_request(path="/v1/internal/tenants"),
                x_regengine_api_key="rge_live_workload.raw-secret",  # pragma: allowlist secret
                throttle=throttle,
            )
        )

    assert exc_info.value.status_code == 403
    assert throttle.failures == 1


def test_workload_key_lifetime_over_90_days_is_denied(monkeypatch):
    now = datetime.now(timezone.utc)
    key = _workload_key(created_at=now, expires_at=now + timedelta(days=91))
    store = _FakeDatabaseStore(key)
    monkeypatch.setattr(mod, "get_key_store", lambda: store)

    with pytest.raises(HTTPException) as exc_info:
        _run(
            mod.require_tenant_provisioner_key(
                request=_request(path="/v1/internal/tenants"),
                x_regengine_api_key="rge_live_workload.raw-secret",  # pragma: allowlist secret
                throttle=_Throttle(),
            )
        )

    assert exc_info.value.status_code == 403


def test_invalid_expired_or_revoked_workload_key_is_unauthorized(monkeypatch):
    store = _FakeDatabaseStore(None)
    monkeypatch.setattr(mod, "get_key_store", lambda: store)
    throttle = _Throttle()

    with pytest.raises(HTTPException) as exc_info:
        _run(
            mod.require_tenant_provisioner_key(
                request=_request(path="/v1/internal/tenants"),
                x_regengine_api_key="rge_live_workload.raw-secret",  # pragma: allowlist secret
                throttle=throttle,
            )
        )

    assert exc_info.value.status_code == 401
    assert throttle.failures == 1


def test_workload_key_rate_limit_is_enforced(monkeypatch):
    store = _FakeDatabaseStore(_workload_key(), allowed=False)
    monkeypatch.setattr(mod, "get_key_store", lambda: store)

    with pytest.raises(HTTPException) as exc_info:
        _run(
            mod.require_tenant_provisioner_key(
                request=_request(path="/v1/internal/tenants"),
                x_regengine_api_key="rge_live_workload.raw-secret",  # pragma: allowlist secret
                throttle=_Throttle(),
            )
        )

    assert exc_info.value.status_code == 429


class _Result:
    def __init__(self, value) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value


def _is_security_guc(statement) -> bool:
    return "set_config('regengine." in str(statement)


def _db_with_query_results(*results):
    """Keep explicit security-GUC writes out of ORM result queues."""

    db = MagicMock()
    remaining = iter(results)

    def _execute(statement, *_args, **_kwargs):
        if _is_security_guc(statement):
            return MagicMock()
        return next(remaining)

    db.execute.side_effect = _execute
    return db


def _non_guc_execute_calls(db):
    return [
        call
        for call in db.execute.call_args_list
        if not _is_security_guc(call.args[0])
    ]


def test_review_tenant_and_reviewer_are_derived_from_active_session(monkeypatch):
    tenant_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    context = _session_context(sysadmin=False, auth_method="email_otp")
    organization_membership = SimpleNamespace(organization_id=tenant_id)
    role = SimpleNamespace(permissions=["review.read"])
    db = _db_with_query_results(_Result(organization_membership), _Result(role))
    monkeypatch.setattr(mod, "get_current_active_session_context", lambda **_kwargs: context)

    actor = _run(
        mod.require_review_read(
            request=_request(headers={"X-Tenant-ID": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"}),
            db=db,
            crypto_service=MagicMock(),
            throttle=_Throttle(),
        )
    )

    assert actor.tenant_id == tenant_id
    assert actor.actor_id == str(context.user.id)
    assert actor.permissions == ("review.read",)


def test_review_read_without_permission_is_denied(monkeypatch):
    context = _session_context(sysadmin=False, auth_method="webauthn")
    db = _db_with_query_results(
        _Result(SimpleNamespace(organization_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")),
        _Result(SimpleNamespace(permissions=[])),
    )
    monkeypatch.setattr(mod, "get_current_active_session_context", lambda **_kwargs: context)

    with pytest.raises(HTTPException) as exc_info:
        _run(
            mod.require_review_read(
                request=_request(path="/v1/admin/review/hallucinations"),
                db=db,
                crypto_service=MagicMock(),
                throttle=_Throttle(),
            )
        )

    assert exc_info.value.status_code == 403


def test_review_decision_requires_high_assurance_before_permission_lookup(monkeypatch):
    context = _session_context(sysadmin=False, auth_method="email_otp")
    db = MagicMock()
    monkeypatch.setattr(mod, "get_current_active_session_context", lambda **_kwargs: context)

    with pytest.raises(HTTPException) as exc_info:
        _run(
            mod.require_review_decide(
                request=_request(path="/v1/admin/review/item/approve"),
                db=db,
                crypto_service=MagicMock(),
                throttle=_Throttle(),
            )
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "requires_step_up"
    assert _non_guc_execute_calls(db) == []


def test_review_approval_passes_only_session_derived_identity(monkeypatch):
    from services.admin.app import review_routes

    captured: dict[str, object] = {}

    class _Tracker:
        def resolve_hallucination(self, review_id, **kwargs):
            captured["review_id"] = review_id
            captured.update(kwargs)
            return True

    user = SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        email="reviewer@example.test",
    )
    actor = mod.PrivilegedActor(
        actor_type="tenant_user",
        actor_id=str(user.id),
        session_id="22222222-2222-2222-2222-222222222222",
        auth_method="webauthn",
        tenant_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        permissions=("review.decide",),
        user=user,
    )
    monkeypatch.setattr(review_routes, "_get_tracker", lambda: _Tracker())

    result = _run(
        review_routes.approve_review_item(
            review_id="review-123",
            request=_request(
                path="/v1/admin/review/review-123/approve",
                headers={"X-Tenant-ID": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"},
            ),
            actor=actor,
        )
    )

    assert result["status"] == "approved"
    assert captured["tenant_id"] == actor.tenant_id
    assert captured["reviewer_id"] == actor.actor_id
    assert captured["actor_user_id"] == actor.actor_id
    assert captured["actor_email"] == user.email


class _AsyncPipeline:
    def __init__(self, redis) -> None:
        self.redis = redis
        self.key = ""

    def incr(self, key):
        self.key = key
        return self

    def expire(self, key, _seconds):
        assert key == self.key
        return self

    async def execute(self):
        self.redis.values[self.key] = self.redis.values.get(self.key, 0) + 1
        return [self.redis.values[self.key], True]


class _AsyncRedis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}

    async def get(self, key):
        return self.values.get(key)

    def pipeline(self, transaction=True):
        assert transaction is True
        return _AsyncPipeline(self)

    async def delete(self, key):
        self.values.pop(key, None)
        return 1


def test_invalid_auth_budget_is_shared_and_resets():
    redis = _AsyncRedis()
    throttle = mod.PrivilegedAuthThrottle(redis_client=redis)

    for _ in range(mod.PRIVILEGED_AUTH_MAX_FAILURES):
        _run(throttle.record_failure("203.0.113.50"))

    assert _run(throttle.is_limited("203.0.113.50")) is True
    _run(throttle.reset("203.0.113.50"))
    assert _run(throttle.is_limited("203.0.113.50")) is False


def test_success_in_review_realm_cannot_reset_workload_failure_budget():
    redis = _AsyncRedis()
    throttle = mod.PrivilegedAuthThrottle(redis_client=redis)
    request = _request(path="/v1/internal/tenants")
    workload_subject = mod._throttle_subject(request, realm=mod._WORKLOAD_AUTH_REALM)
    review_subject = mod._throttle_subject(request, realm=mod._REVIEW_READ_AUTH_REALM)

    assert workload_subject != review_subject
    for _ in range(mod.PRIVILEGED_AUTH_MAX_FAILURES):
        _run(throttle.record_failure(workload_subject))

    # A valid low-privilege review request resets only its own realm.
    _run(throttle.reset(review_subject))
    assert _run(throttle.is_limited(workload_subject)) is True


def test_production_without_redis_fails_closed(monkeypatch):
    monkeypatch.setenv("REGENGINE_ENV", "production")
    throttle = mod.PrivilegedAuthThrottle(redis_client=None)

    with pytest.raises(HTTPException) as exc_info:
        _run(throttle.is_limited("203.0.113.50"))

    assert exc_info.value.status_code == 503


def test_railway_staging_without_redis_fails_closed(monkeypatch):
    monkeypatch.setenv("REGENGINE_ENV", "staging")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")
    throttle = mod.PrivilegedAuthThrottle(redis_client=None)

    with pytest.raises(HTTPException) as exc_info:
        _run(throttle.is_limited("human-admin:203.0.113.50"))

    assert exc_info.value.status_code == 503


def test_explicit_noncloud_test_can_use_memory_throttle(monkeypatch):
    monkeypatch.setenv("REGENGINE_ENV", "test")
    for name in mod.CLOUD_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    throttle = mod.PrivilegedAuthThrottle(redis_client=None)

    assert _run(throttle.is_limited("human-admin:203.0.113.50")) is False


def test_workload_store_subclass_without_shared_rate_limit_backend_fails_closed(monkeypatch):
    store = _FakeDatabaseStore(_workload_key())
    store._redis = None
    monkeypatch.setattr(mod, "get_key_store", lambda: store)

    with pytest.raises(HTTPException) as exc_info:
        _run(
            mod.require_tenant_provisioner_key(
                request=_request(path="/v1/internal/tenants"),
                x_regengine_api_key="rge_live_workload.raw-secret",  # pragma: allowlist secret
                throttle=_Throttle(),
            )
        )

    assert exc_info.value.status_code == 503


def test_admin_and_internal_route_auth_contracts_are_wired_and_internal_is_hidden():
    from services.admin.app import routes

    route_dependencies = {
        (route.path, method): {dependency.call for dependency in route.dependant.dependencies}
        for route in routes.v1_router.routes
        for method in route.methods
    }
    assert routes.require_sysadmin_high_assurance in route_dependencies[("/v1/admin/keys", "GET")]
    assert routes.require_sysadmin_high_assurance in route_dependencies[("/v1/admin/tenants", "POST")]
    assert routes.require_tenant_provisioner_key in route_dependencies[("/v1/internal/tenants", "POST")]

    app = FastAPI()
    app.include_router(routes.v1_router)
    assert "/v1/internal/tenants" not in app.openapi()["paths"]


def test_consumer_health_uses_metrics_credential():
    from services.admin.app import routes

    consumer_route = next(route for route in routes.router.routes if route.path == "/health/consumer")
    dependencies = {dependency.call for dependency in consumer_route.dependant.dependencies}
    assert routes.require_metrics_key in dependencies
    assert routes.require_sysadmin_high_assurance not in dependencies
