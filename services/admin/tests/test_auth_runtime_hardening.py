"""Fail-closed JWT/session runtime and revocation regression tests."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request


def _set_nonproduction(monkeypatch: pytest.MonkeyPatch) -> None:
    from shared.env import CLOUD_ENV_VARS

    monkeypatch.setenv("REGENGINE_ENV", "test")
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("REGENGINE_AUTH_STRICT", raising=False)
    for name in CLOUD_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")


def _set_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGENGINE_ENV", "production")
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/regengine")
    monkeypatch.setenv("REDIS_URL", "redis://example.invalid/0")
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-secret-that-is-long-enough")
    monkeypatch.delenv("AUTH_ALLOW_LEGACY_JTI_FREE", raising=False)
    monkeypatch.delenv("SESSION_STORE_BACKEND", raising=False)
    monkeypatch.delenv("ALLOW_INMEMORY_SESSION_STORE", raising=False)


def _set_railway_staging(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_production(monkeypatch)
    monkeypatch.setenv("REGENGINE_ENV", "staging")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")


def test_access_token_default_is_five_minutes(monkeypatch):
    from services.admin.app.auth_runtime import load_auth_runtime_config

    _set_nonproduction(monkeypatch)
    monkeypatch.delenv("ACCESS_TOKEN_EXPIRE_MINUTES", raising=False)
    assert load_auth_runtime_config().access_token_expire_minutes == 5


@pytest.mark.parametrize("value", ["", "not-a-number", "0", "-1"])
def test_access_token_lifetime_rejects_malformed_or_nonpositive(monkeypatch, value):
    from services.admin.app.auth_runtime import AuthRuntimeConfigurationError, load_auth_runtime_config

    _set_nonproduction(monkeypatch)
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", value)
    with pytest.raises(AuthRuntimeConfigurationError):
        load_auth_runtime_config()


@pytest.mark.parametrize("value", ["16", "60"])
def test_production_access_token_lifetime_rejects_values_above_fifteen(monkeypatch, value):
    from services.admin.app.auth_runtime import AuthRuntimeConfigurationError, load_auth_runtime_config

    _set_production(monkeypatch)
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", value)
    with pytest.raises(AuthRuntimeConfigurationError, match="between 1 and 15"):
        load_auth_runtime_config()


@pytest.mark.parametrize("value", ["1", "15"])
def test_production_access_token_lifetime_accepts_bounds(monkeypatch, value):
    from services.admin.app.auth_runtime import load_auth_runtime_config

    _set_production(monkeypatch)
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", value)
    assert load_auth_runtime_config().access_token_expire_minutes == int(value)


def test_production_rejects_legacy_jti_escape_hatch(monkeypatch):
    from services.admin.app.auth_runtime import AuthRuntimeConfigurationError, load_auth_runtime_config

    _set_production(monkeypatch)
    monkeypatch.setenv("AUTH_ALLOW_LEGACY_JTI_FREE", "true")
    with pytest.raises(AuthRuntimeConfigurationError, match="forbidden"):
        load_auth_runtime_config()


def test_production_never_accepts_jti_free_tokens_even_if_startup_gate_is_bypassed(monkeypatch):
    from services.admin.app import auth_utils

    _set_production(monkeypatch)
    monkeypatch.setenv("AUTH_ALLOW_LEGACY_JTI_FREE", "true")
    assert auth_utils._require_jti_default() is True


@pytest.mark.parametrize(
    ("backend", "allow_in_memory"),
    [("memory", None), ("inmemory", None), ("local", None), ("redis", "true")],
)
def test_production_rejects_in_memory_session_storage(monkeypatch, backend, allow_in_memory):
    from services.admin.app.auth_runtime import AuthRuntimeConfigurationError, load_auth_runtime_config

    _set_production(monkeypatch)
    monkeypatch.setenv("SESSION_STORE_BACKEND", backend)
    if allow_in_memory is not None:
        monkeypatch.setenv("ALLOW_INMEMORY_SESSION_STORE", allow_in_memory)
    with pytest.raises(AuthRuntimeConfigurationError, match="In-memory session"):
        load_auth_runtime_config()


def test_production_requires_redis_url(monkeypatch):
    from services.admin.app.auth_runtime import AuthRuntimeConfigurationError, load_auth_runtime_config

    _set_production(monkeypatch)
    monkeypatch.delenv("REDIS_URL", raising=False)
    with pytest.raises(AuthRuntimeConfigurationError, match="REDIS_URL"):
        load_auth_runtime_config()


def test_railway_staging_requires_production_grade_auth_backends(monkeypatch):
    from services.admin.app.auth_runtime import AuthRuntimeConfigurationError, load_auth_runtime_config

    _set_railway_staging(monkeypatch)
    monkeypatch.delenv("REDIS_URL", raising=False)
    with pytest.raises(AuthRuntimeConfigurationError, match="REDIS_URL"):
        load_auth_runtime_config()

    monkeypatch.setenv("REDIS_URL", "redis://example.invalid/0")
    monkeypatch.setenv("AUTH_ALLOW_LEGACY_JTI_FREE", "true")
    with pytest.raises(AuthRuntimeConfigurationError, match="forbidden"):
        load_auth_runtime_config()


def test_railway_staging_rejects_long_lived_access_tokens(monkeypatch):
    from services.admin.app.auth_runtime import AuthRuntimeConfigurationError, load_auth_runtime_config

    _set_railway_staging(monkeypatch)
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    with pytest.raises(AuthRuntimeConfigurationError, match="between 1 and 15"):
        load_auth_runtime_config()


@pytest.mark.asyncio
async def test_production_runtime_fails_when_redis_ping_fails(monkeypatch):
    import redis.asyncio as aioredis

    from services.admin.app.auth_runtime import AuthRuntimeInitializationError, initialize_auth_runtime

    _set_production(monkeypatch)
    client = MagicMock()
    client.ping = AsyncMock(side_effect=ConnectionError("unavailable"))
    client.aclose = AsyncMock()
    monkeypatch.setattr(aioredis, "from_url", MagicMock(return_value=client))

    with pytest.raises(AuthRuntimeInitializationError, match="Redis is unavailable"):
        await initialize_auth_runtime()
    client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_runtime_wires_and_shuts_down_shared_redis(monkeypatch):
    import redis.asyncio as aioredis
    from shared import jwt_key_registry

    from services.admin.app import auth_utils
    from services.admin.app.auth_runtime import initialize_auth_runtime, shutdown_auth_runtime

    class FakeRedis:
        def __init__(self):
            self.values: dict[str, str] = {}
            self.closed = False

        async def ping(self) -> bool:
            return True

        async def get(self, key: str):
            return self.values.get(key)

        async def set(self, key: str, value: str) -> bool:
            self.values[key] = value
            return True

        async def eval(
            self,
            _script: str,
            _num_keys: int,
            key: str,
            expected_present: str,
            expected: str,
            replacement: str,
        ) -> int:
            current = self.values.get(key)
            matches = (expected_present == "0" and current is None) or (expected_present == "1" and current == expected)
            if not matches:
                return 0
            self.values[key] = replacement
            return 1

        def lock(self, _name: str, **_kwargs):
            lock = asyncio.Lock()

            class FakeLock:
                async def acquire(self) -> bool:
                    await lock.acquire()
                    return True

                async def release(self) -> None:
                    lock.release()

            return FakeLock()

        async def aclose(self) -> None:
            self.closed = True

    _set_production(monkeypatch)
    fake_redis = FakeRedis()
    monkeypatch.setattr(aioredis, "from_url", MagicMock(return_value=fake_redis))

    runtime = await initialize_auth_runtime()
    assert auth_utils._revocation_redis is fake_redis
    assert jwt_key_registry._registry is not None
    assert jwt_key_registry._registry._strict is True

    await shutdown_auth_runtime(runtime)
    assert auth_utils._revocation_redis is None
    assert jwt_key_registry._registry is None
    assert fake_redis.closed is True


@pytest.mark.asyncio
async def test_production_missing_revocation_backend_fails_closed(monkeypatch):
    from services.admin.app import auth_utils
    from services.admin.app.auth_utils import RevocationBackendUnavailable

    _set_production(monkeypatch)
    monkeypatch.setattr(auth_utils, "_revoked_jtis", set())
    monkeypatch.setattr(auth_utils, "_revocation_redis", None)

    with pytest.raises(RevocationBackendUnavailable):
        await auth_utils.check_revoked_async("live-jti")
    with pytest.raises(RevocationBackendUnavailable):
        await auth_utils.revoke_token("new-jti")


@pytest.mark.asyncio
async def test_railway_staging_missing_revocation_backend_fails_closed(monkeypatch):
    from services.admin.app import auth_utils
    from services.admin.app.auth_utils import RevocationBackendUnavailable

    _set_railway_staging(monkeypatch)
    monkeypatch.setattr(auth_utils, "_revoked_jtis", set())
    monkeypatch.setattr(auth_utils, "_revocation_redis", None)

    with pytest.raises(RevocationBackendUnavailable):
        await auth_utils.check_revoked_async("staging-jti")
    with pytest.raises(RevocationBackendUnavailable):
        await auth_utils.revoke_token("staging-jti")


@pytest.mark.asyncio
async def test_production_revocation_read_and_write_errors_fail_closed(monkeypatch):
    from services.admin.app import auth_utils
    from services.admin.app.auth_utils import RevocationBackendUnavailable

    _set_production(monkeypatch)
    monkeypatch.setattr(auth_utils, "_revoked_jtis", set())

    read_failure = MagicMock()
    read_failure.get = AsyncMock(side_effect=ConnectionError("read failed"))
    monkeypatch.setattr(auth_utils, "_revocation_redis", read_failure)
    with pytest.raises(RevocationBackendUnavailable):
        await auth_utils.check_revoked_async("read-jti")

    write_failure = MagicMock()
    write_failure.eval = AsyncMock(side_effect=ConnectionError("write failed"))
    monkeypatch.setattr(auth_utils, "_revocation_redis", write_failure)
    with pytest.raises(RevocationBackendUnavailable):
        await auth_utils.revoke_token("write-jti")


@pytest.mark.asyncio
async def test_shared_backend_revocation_is_visible_to_second_worker(monkeypatch):
    from services.admin.app import auth_utils

    class SharedRedis:
        def __init__(self):
            self.revoked: dict[str, int] = {}

        async def eval(self, _script: str, _num_keys: int, key: str, requested_ttl: int) -> int:
            self.revoked[key] = max(self.revoked.get(key, 0), int(requested_ttl))
            return self.revoked[key]

        async def get(self, key: str):
            return "1" if key in self.revoked else None

        async def sismember(self, _key: str, _value: str) -> bool:
            return False

    _set_production(monkeypatch)
    shared = SharedRedis()
    monkeypatch.setattr(auth_utils, "_revocation_redis", shared)

    # Worker A writes shared state and its own local fast-path cache.
    monkeypatch.setattr(auth_utils, "_revoked_jtis", set())
    await auth_utils.revoke_token("cross-worker-jti")

    # Worker B starts with an empty local cache but reads the same backend.
    monkeypatch.setattr(auth_utils, "_revoked_jtis", set())
    assert await auth_utils.check_revoked_async("cross-worker-jti") is True
    assert "cross-worker-jti" in auth_utils._revoked_jtis


@pytest.mark.asyncio
async def test_auth_dependency_maps_revocation_read_failure_to_503(monkeypatch):
    from services.admin.app import dependencies
    from services.admin.app.auth_utils import RevocationBackendUnavailable

    user_id = uuid.uuid4()
    monkeypatch.setattr(dependencies, "get_supabase", lambda: None)
    monkeypatch.setattr(
        dependencies,
        "decode_access_token",
        lambda _token: {"sub": str(user_id), "jti": "jti", "tv": 0},
    )
    monkeypatch.setattr(
        dependencies,
        "check_revoked_async",
        AsyncMock(side_effect=RevocationBackendUnavailable("down")),
    )
    monkeypatch.setattr(dependencies, "sync_keys_from_registry", AsyncMock())
    db = MagicMock()
    db.bind = None

    with pytest.raises(HTTPException) as exc:
        await dependencies.get_current_user(token="token", db=db)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_auth_dependency_maps_key_registry_failure_to_503(monkeypatch):
    from services.admin.app import dependencies

    _set_production(monkeypatch)
    monkeypatch.setattr(dependencies, "get_supabase", lambda: None)
    monkeypatch.setattr(
        dependencies,
        "sync_keys_from_registry",
        AsyncMock(side_effect=dependencies.JWTKeyRegistryBackendUnavailable("down")),
    )
    decode = MagicMock()
    monkeypatch.setattr(dependencies, "decode_access_token", decode)

    with pytest.raises(HTTPException) as exc:
        await dependencies.get_current_user(token="token", db=MagicMock())
    assert exc.value.status_code == 503
    decode.assert_not_called()


@pytest.mark.asyncio
async def test_production_supabase_bearer_cannot_bypass_local_revocation_backend(monkeypatch):
    from services.admin.app import dependencies

    _set_production(monkeypatch)
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    sb_user = SimpleNamespace(
        id=str(user_id),
        app_metadata={"tenant_id": str(tenant_id), "tv": 0},
    )
    supabase = SimpleNamespace(auth=SimpleNamespace(get_user=MagicMock(return_value=SimpleNamespace(user=sb_user))))
    monkeypatch.setattr(dependencies, "get_supabase", lambda: supabase)
    monkeypatch.setattr(
        dependencies,
        "sync_keys_from_registry",
        AsyncMock(side_effect=dependencies.JWTKeyRegistryBackendUnavailable("redis down")),
    )
    monkeypatch.setattr(dependencies.TenantContext, "set_tenant_context", lambda *_args: None)

    user = SimpleNamespace(
        id=user_id,
        email="user@example.test",
        is_sysadmin=False,
        status="active",
        token_version=0,
    )
    membership = SimpleNamespace(user_id=user_id, tenant_id=tenant_id, is_active=True)
    db = MagicMock()
    db.bind = None
    db.get.return_value = user
    db.execute.return_value.scalar_one_or_none.return_value = membership
    db.execute.return_value.scalars.return_value.all.return_value = [membership]

    with pytest.raises(HTTPException) as exc:
        await dependencies.get_current_user(token="supabase-token", db=db)

    assert exc.value.status_code == 503
    supabase.auth.get_user.assert_not_called()


def _refresh_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/refresh",
            "headers": [],
            "client": ("127.0.0.1", 12345),
        }
    )


def _refresh_session_record(*, idle: bool = False):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        family_id=uuid.uuid4(),
        is_revoked=False,
        created_at=now,
        last_used_at=now - timedelta(days=1) if idle else now,
        expires_at=now + timedelta(days=1),
        token_version=0,
    )


@pytest.mark.asyncio
async def test_refresh_claim_backend_uncertainty_maps_to_503():
    from services.admin.app.auth.refresh_router import RefreshRequest, refresh_session

    store = MagicMock()
    store.claim_session_by_token = AsyncMock(side_effect=ConnectionError("redis down"))

    with pytest.raises(HTTPException) as exc:
        await refresh_session.__wrapped__(
            RefreshRequest(refresh_token="refresh"),
            _refresh_request(),
            db=MagicMock(),
            session_store=store,
        )

    assert exc.value.status_code == 503


@pytest.mark.parametrize("failing_operation", ["check_token_reuse", "get_session", "revoke_all_for_family"])
@pytest.mark.asyncio
async def test_refresh_reuse_backend_uncertainty_maps_to_503(failing_operation):
    from services.admin.app.auth.refresh_router import RefreshRequest, refresh_session

    reused = _refresh_session_record()
    store = MagicMock()
    store.claim_session_by_token = AsyncMock(return_value=None)
    store.check_token_reuse = AsyncMock(return_value=reused.id)
    store.get_session = AsyncMock(return_value=reused)
    store.revoke_all_for_family = AsyncMock(return_value=1)
    getattr(store, failing_operation).side_effect = ConnectionError("redis down")

    with pytest.raises(HTTPException) as exc:
        await refresh_session.__wrapped__(
            RefreshRequest(refresh_token="refresh"),
            _refresh_request(),
            db=MagicMock(),
            session_store=store,
        )

    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_refresh_idle_revoke_backend_uncertainty_maps_to_503(monkeypatch):
    from services.admin.app.auth import refresh_router
    from services.admin.app.auth.refresh_router import RefreshRequest

    session = _refresh_session_record(idle=True)
    store = MagicMock()
    store.claim_session_by_token = AsyncMock(return_value=session)
    store.revoke_session = AsyncMock(side_effect=ConnectionError("redis down"))
    monkeypatch.setattr(refresh_router, "SESSION_IDLE_TIMEOUT_MINUTES", 5)

    with pytest.raises(HTTPException) as exc:
        await refresh_router.refresh_session.__wrapped__(
            RefreshRequest(refresh_token="refresh"),
            _refresh_request(),
            db=MagicMock(),
            session_store=store,
        )

    assert exc.value.status_code == 503


@pytest.mark.parametrize("failing_operation", ["update_session", "mark_token_used"])
@pytest.mark.asyncio
async def test_refresh_rotation_backend_uncertainty_maps_to_503(failing_operation):
    from services.admin.app.auth.refresh_router import RefreshRequest, refresh_session

    session = _refresh_session_record()
    user = SimpleNamespace(id=session.user_id, token_version=0)
    store = MagicMock()
    store.claim_session_by_token = AsyncMock(return_value=session)
    store.update_session = AsyncMock(return_value=True)
    store.mark_token_used = AsyncMock(return_value=True)
    getattr(store, failing_operation).side_effect = ConnectionError("redis down")
    db = MagicMock()
    db.get.return_value = user

    with pytest.raises(HTTPException) as exc:
        await refresh_session.__wrapped__(
            RefreshRequest(refresh_token="refresh"),
            _refresh_request(),
            db=db,
            session_store=store,
        )

    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_logout_maps_revocation_write_failure_to_503(monkeypatch):
    from services.admin.app.auth import sessions_router
    from services.admin.app.auth_utils import RevocationBackendUnavailable

    monkeypatch.setattr(sessions_router, "decode_access_token", lambda _token: {"jti": "jti"})
    monkeypatch.setattr(
        sessions_router,
        "revoke_token",
        AsyncMock(side_effect=RevocationBackendUnavailable("down")),
    )
    monkeypatch.setattr(
        sessions_router,
        "_revoke_all_elevation_tokens_for_user",
        AsyncMock(return_value=0),
    )
    store = MagicMock()
    store.revoke_all_user_sessions = AsyncMock(return_value=0)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/logout",
            "headers": [(b"authorization", b"Bearer token")],
        }
    )

    with pytest.raises(HTTPException) as exc:
        await sessions_router.logout(
            request=request,
            current_user=SimpleNamespace(id=uuid.uuid4()),
            session_store=store,
        )
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_logout_all_commits_durable_invalidation_before_redis_failure(monkeypatch):
    from services.admin.app.auth import sessions_router

    user = SimpleNamespace(id=uuid.uuid4(), token_version=4)
    db = MagicMock()
    db.execute.return_value.rowcount = 2
    db.get.return_value = user
    store = MagicMock()
    store.revoke_all_user_sessions = AsyncMock(side_effect=ConnectionError("down"))
    elevation_cleanup = AsyncMock(side_effect=ConnectionError("down"))
    monkeypatch.setattr(sessions_router, "_revoke_all_elevation_tokens_for_user", elevation_cleanup)

    with pytest.raises(HTTPException) as exc:
        await sessions_router.revoke_all_sessions(current_user=user, db=db, session_store=store)

    assert exc.value.status_code == 503
    assert user.token_version == 5
    db.commit.assert_called_once()
    assert store.revoke_all_user_sessions.await_count == 2
    assert elevation_cleanup.await_count == 2
