"""Limit-matrix tests for per-key quotas (Pattern 2: limits recorded but not enforced).

Every API key records three quotas (``rate_limit_per_minute``,
``rate_limit_per_hour``, ``rate_limit_per_day``), but request auth used to
consult only the minute window: a key far past its hourly or daily cap kept
serving traffic. ``DatabaseAPIKeyStore.check_all_rate_limits`` enforces all
three windows, and ``shared.auth.require_api_key`` calls it on the production
(DB store) branch.

Convention per pattern: for each documented limit, one test with violating
input asserting DENY, one with missing input asserting DENY.
"""

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from shared.api_key_store import APIKeyResponse, DatabaseAPIKeyStore

# Same loading approach as test_auth_1338.py: put services/ on sys.path and
# load shared.auth under its canonical name so this file also runs in
# isolation (plain `import shared.auth` depends on conftest path setup).
_shared_dir = Path(__file__).resolve().parent.parent
_services_dir = _shared_dir.parent
if str(_services_dir) not in sys.path:
    sys.path.insert(0, str(_services_dir))

if "shared.auth" in sys.modules:
    auth = sys.modules["shared.auth"]
else:
    _spec = importlib.util.spec_from_file_location("shared.auth", _shared_dir / "auth.py")
    auth = importlib.util.module_from_spec(_spec)
    sys.modules["shared.auth"] = auth
    _spec.loader.exec_module(auth)

_VALID_TENANT_UUID = "11111111-2222-3333-4444-555555555555"


class _CountingPipeline:
    def __init__(self, redis: "_CountingRedis") -> None:
        self._redis = redis
        self._ops: list[tuple] = []

    def incr(self, key):
        self._ops.append(("incr", key))

    def expire(self, key, seconds):
        self._ops.append(("expire", key, seconds))

    async def execute(self):
        return self._redis.run(self._ops)


class _CountingRedis:
    """Minimal INCR/EXPIRE fake with real per-key counters.

    No TTL expiry: every test below stays inside a single bucket per window,
    so counters only grow, which is all these tests need.
    """

    def __init__(self) -> None:
        self._values: dict[str, int] = {}

    def pipeline(self) -> _CountingPipeline:
        return _CountingPipeline(self)

    def run(self, ops: list[tuple]) -> list:
        count = 0
        for op in ops:
            if op[0] == "incr":
                self._values[op[1]] = self._values.get(op[1], 0) + 1
                count = self._values[op[1]]
        return [count, True]


def _make_store() -> DatabaseAPIKeyStore:
    """Build a DB store without opening a real DB or Redis."""
    store = object.__new__(DatabaseAPIKeyStore)
    store._redis = _CountingRedis()
    return store


def _make_key(**overrides) -> APIKeyResponse:
    fields: dict = {
        "key_id": "rge_testkey",
        "key_prefix": "rge_testkey",
        "name": "quota test key",
        "tenant_id": _VALID_TENANT_UUID,
        "created_at": datetime.now(timezone.utc),
        "rate_limit_per_minute": 1000,
        "rate_limit_per_hour": 1000,
        "rate_limit_per_day": 10000,
    }
    fields.update(overrides)
    return APIKeyResponse(**fields)


async def _use(store: DatabaseAPIKeyStore, key: APIKeyResponse, n: int) -> None:
    for _ in range(n):
        info = await store.check_all_rate_limits(key)
        assert info.allowed


class TestCheckAllRateLimits:
    async def test_all_windows_allow_under_quota(self):
        store, key = _make_store(), _make_key()
        info = await store.check_all_rate_limits(key)
        assert info.allowed
        assert info.limit == 1000  # minute window's info is returned

    async def test_minute_violation_denies(self):
        store, key = _make_store(), _make_key(rate_limit_per_minute=3)
        await _use(store, key, 3)
        assert not (await store.check_all_rate_limits(key)).allowed

    async def test_hour_violation_denies_while_minute_allows(self):
        """Core regression: the hour cap used to be stored but never checked."""
        store, key = _make_store(), _make_key(rate_limit_per_minute=1000, rate_limit_per_hour=3)
        await _use(store, key, 3)
        denied = await store.check_all_rate_limits(key)
        assert not denied.allowed
        assert denied.limit == 3
        assert denied.retry_after is not None and denied.retry_after <= 3600

    async def test_day_violation_denies_while_minute_and_hour_allow(self):
        store, key = (
            _make_store(),
            _make_key(
                rate_limit_per_minute=1000,
                rate_limit_per_hour=1000,
                rate_limit_per_day=3,
            ),
        )
        await _use(store, key, 3)
        denied = await store.check_all_rate_limits(key)
        assert not denied.allowed
        assert denied.limit == 3

    async def test_missing_limit_denies_fail_closed(self):
        """A limit that cannot be evaluated must deny, never allow."""
        store = _make_store()
        key = SimpleNamespace(
            key_id="rge_testkey",
            rate_limit_per_minute=1000,
            rate_limit_per_hour=None,
            rate_limit_per_day=10000,
        )
        denied = await store.check_all_rate_limits(key)
        assert not denied.allowed

    async def test_without_redis_denies_fail_closed(self):
        store, key = _make_store(), _make_key()
        store._redis = None
        assert not (await store.check_all_rate_limits(key)).allowed


def _make_request() -> MagicMock:
    req = MagicMock()
    req.headers = {}
    req.url.path = "/x"
    req.method = "GET"
    return req


class TestRequireApiKeyEnforcesAllWindows:
    async def test_hour_quota_exhaustion_returns_429(self, monkeypatch):
        """End to end through the auth dependency: past the hour cap, 429.

        On the old code this returned the principal (allowed): auth only
        consulted the minute window, so this test fails without the fix.
        """
        monkeypatch.delenv("AUTH_TEST_BYPASS_TOKEN", raising=False)
        monkeypatch.setenv("REGENGINE_ENV", "production")
        key = _make_key(rate_limit_per_minute=1000, rate_limit_per_hour=2)
        store = _make_store()
        store.validate_key = AsyncMock(return_value=key)
        monkeypatch.setattr(auth, "_db_store_instance", store)

        assert await auth.require_api_key(_make_request(), "rge_testkey.secret")
        assert await auth.require_api_key(_make_request(), "rge_testkey.secret")
        with pytest.raises(HTTPException) as exc:
            await auth.require_api_key(_make_request(), "rge_testkey.secret")
        assert exc.value.status_code == 429
        retry_after = int(exc.value.headers["Retry-After"])
        assert 1 <= retry_after <= 3600
