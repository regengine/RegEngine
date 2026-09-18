"""#2699: sticky ``_redis_failed`` flags now retry after a cooldown.

Pre-fix, the first Redis failure in ``stripe_billing/rate_limiting.py``
and ``sandbox/rate_limiting.py`` set ``_redis_failed = True`` for the
process lifetime (logged at DEBUG — invisible in prod), so Redis was
never retried even after it recovered.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from services.ingestion.app.sandbox import rate_limiting as sandbox_rl  # noqa: E402
from services.ingestion.app.stripe_billing import rate_limiting as stripe_rl  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_flags():
    for mod in (stripe_rl, sandbox_rl):
        mod._redis_failed = False
        mod._redis_retry_at = 0.0
        mod._redis_client = None
    yield
    for mod in (stripe_rl, sandbox_rl):
        mod._redis_failed = False
        mod._redis_retry_at = 0.0
        mod._redis_client = None


@pytest.mark.parametrize("mod", [stripe_rl, sandbox_rl], ids=["stripe", "sandbox"])
class TestRedisRetryCooldown:
    def test_failure_arms_cooldown_not_forever(self, mod, monkeypatch):
        """A connect failure marks failed WITH a retry deadline."""

        # get_settings().redis_url pointing nowhere → from_url/ping fails.
        class _S:
            redis_url = "redis://127.0.0.1:1/0"

        if mod is stripe_rl:
            import services.ingestion.app.config as cfg

            monkeypatch.setattr(cfg, "get_settings", lambda: _S())
        else:
            import services.ingestion.app.config as cfg

            monkeypatch.setattr(cfg, "get_settings", lambda: _S())

        assert mod._get_redis() is None
        assert mod._redis_failed is True
        assert mod._redis_retry_at > time.time()

    def test_within_cooldown_no_reconnect_attempt(self, mod):
        mod._redis_failed = True
        mod._redis_retry_at = time.time() + 100
        # No settings patch needed — must return None without trying.
        assert mod._get_redis() is None
        assert mod._redis_failed is True

    def test_after_cooldown_reconnect_is_attempted(self, mod, monkeypatch):
        """Once the cooldown passes, the flag clears and a reconnect runs."""
        attempted = {"n": 0}

        class _S:
            redis_url = "redis://127.0.0.1:1/0"

        import services.ingestion.app.config as cfg

        def _get_settings():
            attempted["n"] += 1
            return _S()

        monkeypatch.setattr(cfg, "get_settings", _get_settings)

        mod._redis_failed = True
        mod._redis_retry_at = time.time() - 1  # cooldown expired

        assert mod._get_redis() is None  # reconnect attempted, still down
        assert attempted["n"] == 1
        # Re-armed for the next cooldown window.
        assert mod._redis_failed is True
        assert mod._redis_retry_at > time.time()
