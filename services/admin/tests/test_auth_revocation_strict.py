"""Strict revocation storage, expiry, retry, and key-registry regressions."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
from fastapi import HTTPException
from shared.jwt_key_registry import (
    REDIS_KEY,
    JWTKeyRegistry,
    JWTKeyRegistryBackendUnavailable,
    SigningKey,
)
from starlette.requests import Request


def _production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGENGINE_ENV", "production")
    monkeypatch.setenv("REDIS_URL", "redis://example.invalid/0")
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-secret-that-is-long-enough")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "5")
    monkeypatch.delenv("AUTH_ALLOW_LEGACY_JTI_FREE", raising=False)
    monkeypatch.delenv("SESSION_STORE_BACKEND", raising=False)
    monkeypatch.delenv("ALLOW_INMEMORY_SESSION_STORE", raising=False)


def _request(token: str = "token") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/logout",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
        }
    )


class ExpiringRedis:
    def __init__(self):
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.legacy_members: set[str] = set()

    async def set(self, key: str, value: str, *, ex: int, nx: bool):
        assert nx is True
        if key in self.values:
            return False
        self.values[key] = value
        self.ttls[key] = ex
        return True

    async def get(self, key: str):
        return self.values.get(key)

    async def eval(self, _script: str, _num_keys: int, key: str, requested_ttl: int):
        requested_ttl = int(requested_ttl)
        if key not in self.values:
            self.values[key] = "1"
            self.ttls[key] = requested_ttl
        else:
            self.ttls[key] = max(self.ttls[key], requested_ttl)
        return self.ttls[key]

    async def sismember(self, _key: str, value: str):
        return value in self.legacy_members


@pytest.mark.asyncio
async def test_revoked_jtis_have_independent_atomic_ttls(monkeypatch):
    from services.admin.app import auth_utils

    _production(monkeypatch)
    redis = ExpiringRedis()
    monkeypatch.setattr(auth_utils, "_revocation_redis", redis)
    monkeypatch.setattr(auth_utils, "_revoked_jtis", set())

    await auth_utils.revoke_token("legacy-60-minute-token", ttl_seconds=3600)
    await auth_utils.revoke_token("new-5-minute-token", ttl_seconds=300)

    long_key = auth_utils._revocation_key("legacy-60-minute-token")
    short_key = auth_utils._revocation_key("new-5-minute-token")
    assert redis.ttls == {long_key: 3600, short_key: 300}

    # An idempotent retry with a shorter estimate must not shorten protection.
    await auth_utils.revoke_token("legacy-60-minute-token", ttl_seconds=60)
    assert redis.ttls[long_key] == 3600

    # The inverse retry order must extend the revocation atomically. A short
    # first estimate must never cap a later, more accurate lifetime.
    await auth_utils.revoke_token("extended-token", ttl_seconds=60)
    extended_key = auth_utils._revocation_key("extended-token")
    await auth_utils.revoke_token("extended-token", ttl_seconds=3600)
    assert redis.ttls[extended_key] == 3600


@pytest.mark.asyncio
async def test_legacy_revocation_set_is_read_only_compatibility(monkeypatch):
    from services.admin.app import auth_utils

    _production(monkeypatch)
    redis = ExpiringRedis()
    redis.legacy_members.add("legacy-jti")
    monkeypatch.setattr(auth_utils, "_revocation_redis", redis)
    monkeypatch.setattr(auth_utils, "_revoked_jtis", set())

    assert await auth_utils.check_revoked_async("legacy-jti") is True
    assert redis.values == {}


@pytest.mark.parametrize("delta", [timedelta(seconds=30), timedelta(minutes=16)])
def test_custom_production_access_token_expiry_cannot_bypass_bounds(monkeypatch, delta):
    from services.admin.app.auth_runtime import AuthRuntimeConfigurationError
    from services.admin.app.auth_utils import create_access_token

    _production(monkeypatch)
    with pytest.raises(AuthRuntimeConfigurationError, match="between 1 and 15"):
        create_access_token({"sub": "user"}, expires_delta=delta)


@pytest.mark.parametrize("delta", [timedelta(minutes=1), timedelta(minutes=15)])
def test_custom_production_access_token_expiry_accepts_bounds(monkeypatch, delta):
    from services.admin.app.auth_utils import create_access_token

    _production(monkeypatch)
    assert create_access_token({"sub": "user"}, expires_delta=delta)


@pytest.mark.asyncio
async def test_logout_passes_actual_remaining_token_lifetime(monkeypatch):
    from services.admin.app.auth import sessions_router

    expires_at = int(time.time()) + 301
    revoke = AsyncMock()
    monkeypatch.setattr(
        sessions_router,
        "decode_access_token",
        lambda _token: {"jti": "jti", "exp": expires_at},
    )
    monkeypatch.setattr(sessions_router, "revoke_token", revoke)
    monkeypatch.setattr(sessions_router, "_revoke_all_elevation_tokens_for_user", AsyncMock(return_value=0))
    store = MagicMock()
    store.revoke_all_user_sessions = AsyncMock(return_value=0)

    result = await sessions_router.logout(
        request=_request(),
        current_user=SimpleNamespace(id=uuid.uuid4()),
        session_store=store,
    )

    assert result == {"status": "success"}
    ttl = revoke.await_args.kwargs["ttl_seconds"]
    assert 299 <= ttl <= 301


@pytest.mark.asyncio
async def test_logout_keeps_bearer_retryable_when_session_cleanup_fails(monkeypatch):
    from services.admin.app.auth import sessions_router

    session_id = uuid.uuid4()
    revoke = AsyncMock()
    store = MagicMock()
    store.get_session = AsyncMock(side_effect=ConnectionError("session backend down"))
    monkeypatch.setattr(
        sessions_router,
        "decode_access_token",
        lambda _token: {"jti": "jti", "sid": str(session_id), "exp": int(time.time()) + 300},
    )
    monkeypatch.setattr(sessions_router, "revoke_token", revoke)
    monkeypatch.setattr(sessions_router, "_revoke_all_elevation_tokens_for_user", AsyncMock(return_value=0))

    with pytest.raises(HTTPException) as exc:
        await sessions_router.logout(
            request=_request(),
            current_user=SimpleNamespace(id=uuid.uuid4()),
            session_store=store,
        )

    assert exc.value.status_code == 503
    revoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_logout_jti_failure_leaves_no_reusable_refresh_or_elevation(monkeypatch):
    from services.admin.app.auth import sessions_router
    from services.admin.app.auth_utils import RevocationBackendUnavailable, hash_token
    from services.admin.app.session_store import InMemorySessionStore, SessionData

    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    refresh_hash = hash_token("refresh")
    store = InMemorySessionStore()
    await store.create_session(
        SessionData(
            id=session_id,
            user_id=user_id,
            refresh_token_hash=refresh_hash,
            family_id=uuid.uuid4(),
            created_at=datetime.now(timezone.utc),
            last_used_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
    )
    client = await store._get_client()
    await client.set("elevation_jti:test", str(user_id), ex=300)
    monkeypatch.setattr(
        sessions_router,
        "decode_access_token",
        lambda _token: {"jti": "jti", "sid": str(session_id), "exp": int(time.time()) + 300},
    )
    monkeypatch.setattr(
        sessions_router,
        "revoke_token",
        AsyncMock(side_effect=RevocationBackendUnavailable("down")),
    )

    with pytest.raises(HTTPException) as exc:
        await sessions_router.logout(
            request=_request(),
            current_user=SimpleNamespace(id=user_id),
            session_store=store,
        )

    assert exc.value.status_code == 503
    assert await store.claim_session_by_token(refresh_hash) is None
    assert await client.get("elevation_jti:test") is None


@pytest.mark.asyncio
async def test_sidless_logout_revokes_all_refresh_sessions_before_jti(monkeypatch):
    from services.admin.app.auth import sessions_router
    from services.admin.app.auth_utils import RevocationBackendUnavailable, hash_token
    from services.admin.app.session_store import InMemorySessionStore, SessionData

    user_id = uuid.uuid4()
    refresh_hash = hash_token("sidless-refresh")
    store = InMemorySessionStore()
    await store.create_session(
        SessionData(
            id=uuid.uuid4(),
            user_id=user_id,
            refresh_token_hash=refresh_hash,
            family_id=uuid.uuid4(),
            created_at=datetime.now(timezone.utc),
            last_used_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
    )
    revoke_jti = AsyncMock(side_effect=RevocationBackendUnavailable("redis down"))
    monkeypatch.setattr(
        sessions_router,
        "decode_access_token",
        lambda _token: {"jti": "sidless-jti", "exp": int(time.time()) + 300},
    )
    monkeypatch.setattr(sessions_router, "revoke_token", revoke_jti)
    monkeypatch.setattr(
        sessions_router,
        "_revoke_all_elevation_tokens_for_user",
        AsyncMock(return_value=0),
    )

    with pytest.raises(HTTPException) as exc:
        await sessions_router.logout(
            request=_request(),
            current_user=SimpleNamespace(id=user_id),
            session_store=store,
        )

    assert exc.value.status_code == 503
    assert await store.claim_session_by_token(refresh_hash) is None
    assert revoke_jti.await_count == 2  # one bounded idempotent retry


@pytest.mark.asyncio
async def test_logout_all_cleanup_failure_still_invalidates_old_jwts(monkeypatch):
    from services.admin.app import dependencies
    from services.admin.app.auth import sessions_router
    from services.admin.app.auth_utils import create_access_token

    monkeypatch.setenv("REGENGINE_ENV", "test")
    monkeypatch.setattr(dependencies, "get_supabase", lambda: None)
    monkeypatch.setattr(dependencies, "check_revoked_async", AsyncMock(return_value=False))

    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    user = SimpleNamespace(
        id=user_id,
        email="user@example.test",
        is_sysadmin=False,
        status="active",
        token_version=4,
    )
    old_token = create_access_token({"sub": str(user_id), "tenant_id": str(tenant_id), "tv": 4})
    db = MagicMock()
    db.bind = None
    db.get.return_value = user
    db.execute.return_value.rowcount = 0
    store = MagicMock()
    store.revoke_all_user_sessions = AsyncMock(side_effect=ConnectionError("down"))
    monkeypatch.setattr(
        sessions_router,
        "_revoke_all_elevation_tokens_for_user",
        AsyncMock(side_effect=ConnectionError("down")),
    )

    with pytest.raises(HTTPException) as logout_exc:
        await sessions_router.revoke_all_sessions(
            current_user=user,
            db=db,
            session_store=store,
        )
    assert logout_exc.value.status_code == 503
    assert user.token_version == 5

    # Any access/elevation JWT minted before the durable version bump is now
    # unusable even though Redis cleanup could not complete.
    with pytest.raises(HTTPException) as replay_exc:
        await dependencies.get_current_user(token=old_token, db=db)
    assert replay_exc.value.status_code == 401


class RegistryRedis:
    def __init__(self):
        self.store: dict[str, str] = {}
        self.read_error = False
        self.write_error = False
        self.set_count = 0
        self.fail_on_set: int | None = None
        self.mutation_lock = asyncio.Lock()
        self.mutation_lock_owner: asyncio.Task | None = None

    async def get(self, key: str):
        if self.read_error:
            raise ConnectionError("read failed")
        return self.store.get(key)

    async def set(self, key: str, value: str):
        self.set_count += 1
        if self.write_error or self.set_count == self.fail_on_set:
            raise ConnectionError("write failed")
        self.store[key] = value
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
        self.set_count += 1
        if self.write_error or self.set_count == self.fail_on_set:
            raise ConnectionError("write failed")
        current = self.store.get(key)
        matches = (expected_present == "0" and current is None) or (expected_present == "1" and current == expected)
        if not matches:
            return 0
        self.store[key] = replacement
        return 1

    def lock(self, _name: str, **_kwargs):
        return RegistryLock(self)


class RegistryLock:
    def __init__(self, redis: RegistryRedis):
        self._redis = redis

    async def acquire(self) -> bool:
        await self._redis.mutation_lock.acquire()
        self._redis.mutation_lock_owner = asyncio.current_task()
        return True

    async def release(self) -> None:
        assert self._redis.mutation_lock_owner is asyncio.current_task()
        self._redis.mutation_lock_owner = None
        self._redis.mutation_lock.release()


class InterleavingRegistryRedis(RegistryRedis):
    """Force stale rotate to commit after revoke unless a shared lock is used."""

    def __init__(self):
        super().__init__()
        self._initial_reads = 0
        self._both_initial_reads = asyncio.Event()
        self.cas_conflicts = 0

    async def get(self, key: str):
        snapshot = await super().get(key)
        self._initial_reads += 1
        if self._initial_reads <= 2:
            if self._initial_reads == 2:
                self._both_initial_reads.set()
            await self._both_initial_reads.wait()
            return snapshot
        return await super().get(key)

    async def eval(self, *args, **kwargs):
        committed = await super().eval(*args, **kwargs)
        if committed == 0:
            self.cas_conflicts += 1
        return committed


@pytest.mark.asyncio
async def test_concurrent_rotation_cannot_resurrect_revoked_key():
    redis = InterleavingRegistryRedis()
    redis.store[REDIS_KEY] = json.dumps(
        [
            {
                "kid": "old",
                "secret": "old-secret",  # pragma: allowlist secret
                "algorithm": "HS256",
                "created_at": time.time(),
                "expires_at": None,
                "is_active": True,
                "is_valid": True,
                "rotated_by": None,
            }
        ]
    )
    revoker = JWTKeyRegistry(redis_client=redis, strict=True)
    rotator = JWTKeyRegistry(redis_client=redis, strict=True)

    await asyncio.gather(
        revoker.revoke_key("old", revoked_by="replica-a"),
        rotator.rotate(rotated_by="replica-b"),
    )

    keys = json.loads(redis.store[REDIS_KEY])
    old = next(item for item in keys if item["kid"] == "old")
    assert old["is_valid"] is False
    assert len([item for item in keys if item["is_active"] and item["is_valid"]]) == 1
    assert redis.cas_conflicts >= 1


@pytest.mark.asyncio
async def test_strict_key_registry_fails_closed_on_reads_and_writes(monkeypatch):
    monkeypatch.setenv("AUTH_SECRET_KEY", "registry-test-secret")
    redis = RegistryRedis()
    registry = JWTKeyRegistry(redis_client=redis, strict=True)
    await registry.initialize()

    redis.read_error = True
    with pytest.raises(JWTKeyRegistryBackendUnavailable):
        await registry.get_verification_keys()

    redis.read_error = False
    redis.write_error = True
    with pytest.raises(JWTKeyRegistryBackendUnavailable):
        await registry.rotate()


@pytest.mark.asyncio
async def test_shared_registry_mutation_does_not_require_redis_lock(monkeypatch):
    monkeypatch.setenv("AUTH_SECRET_KEY", "registry-test-secret")
    redis = RegistryRedis()
    registry = JWTKeyRegistry(redis_client=redis, strict=False)
    await registry.initialize()
    redis.lock = None  # type: ignore[method-assign]

    rotated = await registry.rotate()
    assert rotated.is_active is True


@pytest.mark.asyncio
async def test_strict_registry_rotation_is_visible_across_replicas(monkeypatch):
    monkeypatch.setenv("AUTH_SECRET_KEY", "registry-test-secret")
    redis = RegistryRedis()
    first = JWTKeyRegistry(redis_client=redis, strict=True)
    second = JWTKeyRegistry(redis_client=redis, strict=True)
    await first.initialize()
    await second.initialize()

    old_kid = (await second.get_signing_key()).kid
    new_key = await first.rotate(rotated_by="replica-a")
    replica_b_keys = await second.get_verification_keys()

    assert {key.kid for key in replica_b_keys} == {old_kid, new_key.kid}
    assert json.loads(redis.store[REDIS_KEY])


@pytest.mark.asyncio
async def test_worker_auth_cache_observes_rotation_from_another_replica(monkeypatch):
    import shared.jwt_key_registry as key_registry_module

    from services.admin.app import auth_utils

    monkeypatch.setenv("AUTH_SECRET_KEY", "registry-test-secret")
    redis = RegistryRedis()
    first = JWTKeyRegistry(redis_client=redis, strict=True)
    second = JWTKeyRegistry(redis_client=redis, strict=True)
    await first.initialize()
    await second.initialize()
    monkeypatch.setattr(key_registry_module, "_registry", second)

    old_key = await second.get_signing_key()
    auth_utils._sync_keys_from_registry(old_key, [old_key])
    new_key = await first.rotate(rotated_by="replica-a")

    await auth_utils.sync_keys_from_registry()
    assert auth_utils._active_kid == new_key.kid
    assert set(auth_utils._verification_keys) == {old_key.kid, new_key.kid}


@pytest.mark.asyncio
async def test_worker_auth_cache_observes_emergency_revoke_from_another_replica(monkeypatch):
    import shared.jwt_key_registry as key_registry_module

    from services.admin.app import auth_utils

    monkeypatch.setenv("AUTH_SECRET_KEY", "registry-test-secret")
    redis = RegistryRedis()
    first = JWTKeyRegistry(redis_client=redis, strict=True)
    second = JWTKeyRegistry(redis_client=redis, strict=True)
    await first.initialize()
    await second.initialize()
    monkeypatch.setattr(key_registry_module, "_registry", second)

    old_key = await second.get_signing_key()
    auth_utils._sync_keys_from_registry(old_key, [old_key])
    assert await first.revoke_key(old_key.kid) is True

    await auth_utils.sync_keys_from_registry()
    assert old_key.kid not in auth_utils._verification_keys
    assert auth_utils._active_kid != old_key.kid


def test_revoked_legacy_secret_cannot_bypass_registry_by_omitting_kid(monkeypatch):
    """Once the registry is authoritative, the static secret is not a bypass."""

    from services.admin.app import auth_utils

    current = SigningKey(kid="current", secret="current-secret")
    monkeypatch.setattr(auth_utils, "_active_kid", auth_utils._active_kid)
    monkeypatch.setattr(auth_utils, "_active_secret", auth_utils._active_secret)
    monkeypatch.setattr(auth_utils, "_verification_keys", auth_utils._verification_keys)
    auth_utils._sync_keys_from_registry(current, [current])
    monkeypatch.setattr(auth_utils, "_revoked_jtis", set())

    forged = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "jti": str(uuid.uuid4()),
            "aud": auth_utils.SESSION_AUDIENCE,
            "iss": auth_utils.SESSION_ISSUER,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        auth_utils.SECRET_KEY,
        algorithm=auth_utils.ALGORITHM,
        # Deliberately omit kid: this used to reach the unconditional static
        # SECRET_KEY fallback even after that key was revoked in the registry.
    )

    with pytest.raises(jwt.exceptions.InvalidSignatureError):
        auth_utils.decode_access_token(forged)


def test_kidless_legacy_token_still_uses_a_valid_registry_key(monkeypatch):
    """Compatibility remains while the legacy key is still registry-valid."""

    from services.admin.app import auth_utils

    legacy = SigningKey(kid="legacy-valid", secret=auth_utils.SECRET_KEY)
    current = SigningKey(kid="current", secret="current-secret", created_at=legacy.created_at + 1)
    monkeypatch.setattr(auth_utils, "_active_kid", auth_utils._active_kid)
    monkeypatch.setattr(auth_utils, "_active_secret", auth_utils._active_secret)
    monkeypatch.setattr(auth_utils, "_verification_keys", auth_utils._verification_keys)
    auth_utils._sync_keys_from_registry(current, [legacy, current])
    monkeypatch.setattr(auth_utils, "_revoked_jtis", set())

    token = jwt.encode(
        {
            "sub": "legacy-user",
            "jti": str(uuid.uuid4()),
            "aud": auth_utils.SESSION_AUDIENCE,
            "iss": auth_utils.SESSION_ISSUER,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        legacy.secret,
        algorithm=auth_utils.ALGORITHM,
    )

    assert auth_utils.decode_access_token(token)["sub"] == "legacy-user"


def test_static_secret_remains_available_only_before_local_registry_bootstrap(monkeypatch):
    """Local startup keeps its historical static-key compatibility boundary."""

    from services.admin.app import auth_utils

    monkeypatch.setenv("REGENGINE_ENV", "test")
    monkeypatch.setattr(auth_utils, "_active_kid", None)
    monkeypatch.setattr(auth_utils, "_active_secret", None)
    monkeypatch.setattr(auth_utils, "_verification_keys", {})
    monkeypatch.setattr(auth_utils, "_revoked_jtis", set())
    token = jwt.encode(
        {
            "sub": "local-user",
            "jti": str(uuid.uuid4()),
            "aud": auth_utils.SESSION_AUDIENCE,
            "iss": auth_utils.SESSION_ISSUER,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        auth_utils.SECRET_KEY,
        algorithm=auth_utils.ALGORITHM,
    )

    assert auth_utils.decode_access_token(token)["sub"] == "local-user"


class CrashSafeCASRedis:
    """Redis double that supports CAS but rejects the retired mutex API."""

    def __init__(self):
        self.store: dict[str, str] = {"regengine:jwt:keys:mutation-lock": "abandoned-owner"}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str):
        self.store[key] = value
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
        current = self.store.get(key)
        matches = (expected_present == "0" and current is None) or (expected_present == "1" and current == expected)
        if not matches:
            return 0
        self.store[key] = replacement
        return 1

    def lock(self, *_args, **_kwargs):
        raise AssertionError("JWT registry must not depend on a crash-persistent Redis mutex")


@pytest.mark.asyncio
async def test_abandoned_legacy_lock_cannot_disable_registry_mutations(monkeypatch):
    """A crashed old writer must not permanently block rotation or revocation."""

    monkeypatch.setenv("AUTH_SECRET_KEY", "registry-test-secret")
    redis = CrashSafeCASRedis()
    registry = JWTKeyRegistry(redis_client=redis, strict=True)

    await registry.initialize()
    old = await registry.get_signing_key()
    rotated = await registry.rotate(rotated_by="replica-after-crash")
    assert rotated.kid != old.kid
    assert await registry.revoke_key(old.kid, revoked_by="incident-response") is True
    assert redis.store["regengine:jwt:keys:mutation-lock"] == "abandoned-owner"


@pytest.mark.asyncio
async def test_key_revocation_recovers_after_partial_replacement_failure(monkeypatch):
    monkeypatch.setenv("AUTH_SECRET_KEY", "registry-test-secret")
    redis = RegistryRedis()
    registry = JWTKeyRegistry(redis_client=redis, strict=True)
    await registry.initialize()  # set #1

    # Revocation and replacement are one atomic registry write (set #2). A
    # failed write must leave the prior active key intact, never persist a
    # durable no-active-key intermediate state.
    redis.fail_on_set = 2
    with pytest.raises(JWTKeyRegistryBackendUnavailable):
        await registry.revoke_key("re-legacy-0001")
    signing_key, verification_keys = await registry.get_key_snapshot()
    assert signing_key.kid == "re-legacy-0001"
    assert [key.kid for key in verification_keys] == ["re-legacy-0001"]

    redis.fail_on_set = None
    assert await registry.revoke_key("re-legacy-0001") is True
    active = [key for key in await registry.get_all_keys() if key.is_active and key.is_valid]
    assert len(active) == 1


@pytest.mark.asyncio
async def test_system_key_revocation_routes_map_backend_failure_to_503(monkeypatch):
    import shared.jwt_key_registry as key_registry_module

    from services.admin.app import auth_utils as runtime_auth_utils, system_routes

    unavailable = key_registry_module.JWTKeyRegistryBackendUnavailable("down")
    monkeypatch.setattr(
        key_registry_module,
        "get_key_registry",
        AsyncMock(side_effect=unavailable),
    )

    with pytest.raises(HTTPException) as key_exc:
        await system_routes.revoke_jwt_key("kid", current_user=SimpleNamespace())
    assert key_exc.value.status_code == 503

    monkeypatch.setattr(
        runtime_auth_utils,
        "revoke_all_jwt_keys",
        AsyncMock(side_effect=unavailable),
    )
    with pytest.raises(HTTPException) as all_exc:
        await system_routes.revoke_all_jwt_keys(current_user=SimpleNamespace())
    assert all_exc.value.status_code == 503


@pytest.mark.asyncio
async def test_system_jti_revocation_uses_canonical_auth_utils_module(monkeypatch):
    from services.admin.app import auth_utils, system_routes

    revoke = AsyncMock()
    monkeypatch.setattr(auth_utils, "revoke_token", revoke)

    result = await system_routes.revoke_jwt_token("canonical-jti", current_user=SimpleNamespace())

    assert result == {"status": "revoked", "jti": "canonical-jti"}
    revoke.assert_awaited_once_with("canonical-jti")
