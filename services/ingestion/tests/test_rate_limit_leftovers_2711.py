"""#2711: ingestion-side rate-limit leftovers.

* ``authz`` auth-failure block migrated from a bare module-level dict to
  ``shared.rate_limit.BruteForceLimiter`` (the #1392 admin pattern) —
  Redis-shared when available, loud per-process fallback otherwise.
* Sandbox share-bucket dict gains stale-bucket eviction past a cap.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

import importlib  # noqa: E402

from app import authz  # noqa: E402

# The package re-exports its APIRouter as ``router``, shadowing the module —
# resolve the MODULE explicitly.
sandbox_router = importlib.import_module("app.sandbox.router")


# ---------------------------------------------------------------------------
# authz → BruteForceLimiter
# ---------------------------------------------------------------------------


class TestAuthFailureLimiter:
    @pytest.fixture(autouse=True)
    def _fresh_limiter(self, monkeypatch):
        from shared.rate_limit import BruteForceLimiter

        limiter = BruteForceLimiter(
            namespace="test-ingestion-auth",
            max_failures=authz._AUTH_FAIL_MAX,
            window_seconds=authz._AUTH_FAIL_WINDOW,
            redis_client=None,  # force the per-process counter for the test
        )
        limiter._redis = None  # ensure no env Redis was picked up
        monkeypatch.setattr(authz, "_auth_limiter", limiter)
        yield

    def test_blocks_after_max_failures(self):
        for _ in range(authz._AUTH_FAIL_MAX):
            authz._record_auth_failure("10.9.8.7")

        with pytest.raises(HTTPException) as exc_info:
            authz._check_auth_rate_limit("10.9.8.7")
        assert exc_info.value.status_code == 429

    def test_below_threshold_passes(self):
        for _ in range(authz._AUTH_FAIL_MAX - 1):
            authz._record_auth_failure("10.9.8.8")
        authz._check_auth_rate_limit("10.9.8.8")  # must not raise

    def test_ips_are_independent(self):
        for _ in range(authz._AUTH_FAIL_MAX):
            authz._record_auth_failure("10.0.0.1")
        authz._check_auth_rate_limit("10.0.0.2")  # other IP unaffected

    def test_uses_brute_force_limiter_backend(self, monkeypatch):
        """The block decision comes from BruteForceLimiter.is_limited —
        i.e. a Redis-shared budget when Redis is configured."""
        fake = MagicMock()
        fake.is_limited.return_value = True
        monkeypatch.setattr(authz, "_auth_limiter", fake)

        with pytest.raises(HTTPException):
            authz._check_auth_rate_limit("10.1.1.1")
        fake.is_limited.assert_called_once_with("10.1.1.1")

    def test_module_dict_is_gone(self):
        """The pre-#2711 per-process dict must not come back."""
        assert not hasattr(authz, "_auth_failures")


# ---------------------------------------------------------------------------
# Sandbox share-bucket eviction
# ---------------------------------------------------------------------------


class TestShareBucketEviction:
    @pytest.fixture(autouse=True)
    def _fresh_buckets(self, monkeypatch):
        monkeypatch.setattr(sandbox_router, "_share_buckets", {})
        yield

    def test_under_cap_no_eviction(self, monkeypatch):
        monkeypatch.setattr(sandbox_router, "_SHARE_BUCKET_CAP", 10)
        now = 1_000_000.0
        sandbox_router._share_buckets.update({f"ip-{i}": [] for i in range(5)})
        sandbox_router._evict_stale_share_buckets(now)
        assert len(sandbox_router._share_buckets) == 5  # untouched below cap

    def test_over_cap_evicts_stale_keeps_fresh(self, monkeypatch):
        monkeypatch.setattr(sandbox_router, "_SHARE_BUCKET_CAP", 3)
        now = 1_000_000.0
        stale = now - sandbox_router._SHARE_WINDOW - 10
        sandbox_router._share_buckets.update(
            {
                "empty": [],
                "aged": [stale],
                "fresh-1": [now - 5],
                "fresh-2": [now - 1],
            }
        )
        sandbox_router._evict_stale_share_buckets(now)
        assert set(sandbox_router._share_buckets) == {"fresh-1", "fresh-2"}
